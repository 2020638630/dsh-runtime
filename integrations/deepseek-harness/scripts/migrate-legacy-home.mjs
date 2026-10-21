#!/usr/bin/env node
/** Copy Session data into a new Home and remove the retired private pin event.
 *
 * This deliberately never edits the source Home. The original compressed
 * Session file is archived in the destination before any migrated copy is
 * written. The policy identity moves to the plugin's durable pin sidecar.
 */
import { createHash } from 'node:crypto'
import { cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, writeFileSync } from 'node:fs'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { zstdCompressSync, zstdDecompressSync } from 'node:zlib'

const PRIVATE_EVENT = 'subagent/governance-policy-pin'
const SESSION_ID = /^session-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const HASH = /^[0-9a-f]{64}$/u
const MAGIC = [0x28, 0xb5, 0x2f, 0xfd]
const SEQUENCE_FIELDS = new Set(['seq', 'messageSeqs', 'sourceEventSeqs', 'throughSeq'])
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')

function argumentsFrom(argv) {
  const values = new Map()
  let apply = false
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === '--apply') { apply = true; continue }
    if (!['--source-home', '--destination-home'].includes(argv[index]) || !argv[index + 1])
      throw new Error('usage: migrate-legacy-home --source-home ABS --destination-home ABS [--apply]')
    if (values.has(argv[index])) throw new Error(`duplicate argument ${argv[index]}`)
    values.set(argv[index], argv[++index])
  }
  const sourceHome = values.get('--source-home')
  const destinationHome = values.get('--destination-home')
  if (!sourceHome || !destinationHome || !isAbsolute(sourceHome) || !isAbsolute(destinationHome))
    throw new Error('both Home paths must be absolute')
  const source = realpathSync(sourceHome)
  const requestedDestination = resolve(destinationHome)
  const parent = realpathSync(dirname(requestedDestination))
  if (!lstatSync(parent).isDirectory()) throw new Error('destination parent must exist')
  const destination = join(parent, basename(requestedDestination))
  const relation = relative(source, destination)
  if (relation === '' || (relation !== '..' && !relation.startsWith(`..${sep}`) && !isAbsolute(relation)))
    throw new Error('destination must be outside the source Home')
  if (existsSync(destination)) throw new Error('destination already exists')
  return { source, destination, apply }
}

function walkFiles(root) {
  const files = []
  function walk(directory) {
    for (const item of readdirSync(directory, { withFileTypes: true })) {
      const full = join(directory, item.name)
      const info = lstatSync(full)
      if (info.isSymbolicLink()) throw new Error('source sessions contain a link')
      if (info.isDirectory()) walk(full)
      else if (info.isFile()) files.push(full)
      else throw new Error('source sessions contain an unsupported entry')
    }
  }
  walk(root)
  return files
}

function decodeFrames(bytes) {
  const starts = []
  for (let offset = 0; offset < bytes.length - 3; offset++) {
    if (MAGIC.every((value, index) => bytes[offset + index] === value)) starts.push(offset)
  }
  if (starts[0] !== 0) throw new Error('Session file does not start with a Zstd frame')
  starts.push(bytes.length)
  return starts.slice(0, -1).map((start, index) => {
    const decoded = zstdDecompressSync(bytes.subarray(start, starts[index + 1])).toString('utf8')
    return decoded.trimEnd().split(/\r?\n/u).filter(Boolean).map(JSON.parse)
  })
}

function checkIdentity(identity) {
  if (!identity || typeof identity !== 'object' || Array.isArray(identity)
    || !['policy_id', 'policy_version', 'artifact_schema_version'].every(key =>
      typeof identity[key] === 'string' && identity[key].length > 0)
    || !HASH.test(identity.policy_hash ?? '')) throw new Error('legacy policy identity is invalid')
}

function sequenceKeys(record, found = new Set()) {
  if (!record || typeof record !== 'object') return found
  for (const [key, value] of Object.entries(record)) {
    if (/seq/iu.test(key)) found.add(key)
    sequenceKeys(value, found)
  }
  return found
}

function adjustReferences(record, removedSeq) {
  if (Array.isArray(record)) return record.map(item => adjustReferences(item, removedSeq))
  if (!record || typeof record !== 'object') return record
  const changed = {}
  for (const [key, value] of Object.entries(record)) {
    if ((key === 'messageSeqs' || key === 'sourceEventSeqs') && Array.isArray(value)) {
      if (value.includes(removedSeq)) throw new Error('legacy event has a direct sequence reference')
      changed[key] = value.map(seq => typeof seq === 'number' && seq > removedSeq ? seq - 1 : seq)
    } else if (key === 'throughSeq' && typeof value === 'number') {
      changed[key] = value >= removedSeq ? value - 1 : value
    } else changed[key] = adjustReferences(value, removedSeq)
  }
  return changed
}

function withoutSequence(record) {
  if (Array.isArray(record)) return record.map(withoutSequence)
  if (!record || typeof record !== 'object') return record
  return Object.fromEntries(Object.entries(record)
    .filter(([key]) => !SEQUENCE_FIELDS.has(key))
    .map(([key, value]) => [key, withoutSequence(value)]))
}

function migrate(frames) {
  const original = frames.flat()
  const pins = original.filter(event => event.type === PRIVATE_EVENT)
  if (pins.length !== 1 || !Number.isInteger(pins[0].seq))
    throw new Error('expected one legacy governance event')
  const pin = pins[0]
  checkIdentity(pin.data)
  const seqs = original.filter(event => Number.isInteger(event.seq))
  if (!seqs.every((event, index) => event.seq === index))
    throw new Error('source Session sequence is not contiguous')
  const unknown = [...sequenceKeys(original)].filter(key => !SEQUENCE_FIELDS.has(key))
  if (unknown.length > 0) throw new Error('unrecognized sequence references in legacy Session')
  const changed = frames.map(events => events.filter(event => event !== pin).map(event => {
    const next = adjustReferences(event, pin.seq)
    if (Number.isInteger(next.seq) && next.seq > pin.seq) next.seq--
    return next
  }))
  const after = changed.flat()
  const afterSeqs = after.filter(event => Number.isInteger(event.seq))
  if (!afterSeqs.every((event, index) => event.seq === index))
    throw new Error('migrated Session sequence is not contiguous')
  const expected = original.filter(event => event !== pin)
  if (JSON.stringify(expected.map(withoutSequence)) !== JSON.stringify(after.map(withoutSequence)))
    throw new Error('migration changed non-governance Session content')
  return { frames: changed, identity: pin.data, removedSeq: pin.seq,
    originalEvents: original.length, migratedEvents: after.length }
}

function main() {
  const { source, destination, apply } = argumentsFrom(process.argv.slice(2))
  const sourceSessions = join(source, 'sessions')
  if (!lstatSync(sourceSessions).isDirectory()) throw new Error('source sessions directory is missing')
  const files = walkFiles(sourceSessions)
  const planned = []
  const sessionIds = new Set()
  for (const file of files) {
    const relativePath = relative(sourceSessions, file)
    const sessionId = relativePath.split(sep).find(part => SESSION_ID.test(part))
    if (sessionId) sessionIds.add(sessionId)
    if (!file.endsWith('.zstd')) continue
    const bytes = readFileSync(file)
    const frames = decodeFrames(bytes)
    if (!frames.flat().some(event => event.type === PRIVATE_EVENT)) continue
    if (!sessionId || !file.endsWith('session.v4.jsonl.zstd'))
      throw new Error('unsupported private event location')
    const result = migrate(frames)
    planned.push({ relativePath, sessionId, sourceHash: sha256(bytes), ...result })
  }
  if (new Set(planned.map(item => item.sessionId)).size !== planned.length)
    throw new Error('multiple legacy files share a Session identity')
  const report = { schema_version: 1, source_home: source, destination_home: destination,
    session_count: sessionIds.size, copied_file_count: files.length,
    migrated_session_count: planned.length,
    migrated: planned.map(({ sessionId, sourceHash, removedSeq, originalEvents, migratedEvents }) =>
      ({ session_id: sessionId, source_sha256: sourceHash, removed_seq: removedSeq,
        original_events: originalEvents, migrated_events: migratedEvents })) }
  if (!apply) { process.stdout.write(`${JSON.stringify({ mode: 'plan', ...report })}\n`); return }

  mkdirSync(destination)
  cpSync(sourceSessions, join(destination, 'sessions'), { recursive: true, force: false, errorOnExist: true })
  mkdirSync(join(destination, 'archive'))
  mkdirSync(join(destination, 'pins'))
  for (const item of planned) {
    const target = join(destination, 'sessions', item.relativePath)
    const copied = readFileSync(target)
    if (sha256(copied) !== item.sourceHash) throw new Error('copied Session hash differs from source')
    const archived = join(destination, 'archive', `${item.sessionId}.original.zstd`)
    writeFileSync(archived, copied, { flag: 'wx' })
    const pin = join(destination, 'pins', `${item.sessionId}.json`)
    writeFileSync(pin, `${JSON.stringify({ schema_version: 1, session_id: item.sessionId, policy_identity: item.identity })}\n`, { flag: 'wx' })
    const encoded = Buffer.concat(item.frames.map(events => zstdCompressSync(Buffer.from(`${events.map(event => JSON.stringify(event)).join('\n')}\n`, 'utf8'))))
    const pending = `${target}.migrating`
    writeFileSync(pending, encoded, { flag: 'wx' })
    renameSync(pending, target)
    if (sha256(readFileSync(archived)) !== item.sourceHash) throw new Error('archived Session hash differs from source')
  }
  writeFileSync(join(destination, 'migration-report.json'), `${JSON.stringify(report, null, 2)}\n`, { flag: 'wx' })
  process.stdout.write(`${JSON.stringify({ mode: 'applied', sessionCount: sessionIds.size,
    copiedFiles: files.length, migratedSessions: planned.length })}\n`)
}

main()
