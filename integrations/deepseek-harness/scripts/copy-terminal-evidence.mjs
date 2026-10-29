#!/usr/bin/env node
/** Explicit, one-run copy of historical Runtime evidence. Never rewrites the source Manifest. */
import { createHash, randomUUID } from 'node:crypto'
import { constants } from 'node:fs'
import { lstat, mkdir, open, readdir, realpath, rename, stat, writeFile } from 'node:fs/promises'
import { basename, dirname, isAbsolute, join, relative, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const SAFE_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/u
const MAX_FILES = 32
const MAX_TOTAL_BYTES = 64 * 1_048_576
const MAX_FILE_BYTES = 32 * 1_048_576
const MAX_MANIFEST_BYTES = 1_048_576
const MAX_DIFF_BYTES = 8 * 1_048_576
const hash = bytes => createHash('sha256').update(bytes).digest('hex')

function within(root, child) {
  const rel = relative(root, child)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

function failure(code) {
  const error = new Error(code)
  error.code = code
  return error
}

async function readBoundedFile(runDir, name, maxBytes) {
  for (const part of name.split(/[\\/]/u)) validateName(part)
  const path = join(runDir, ...name.split('/'))
  const entry = await lstat(path)
  if (!entry.isFile() || entry.isSymbolicLink() || entry.nlink !== 1 || entry.size > maxBytes) {
    throw failure('UNSAFE_ARTIFACT')
  }
  const physical = await realpath(path)
  if (!within(runDir, physical) || basename(physical) !== basename(name)) throw failure('UNSAFE_ARTIFACT')
  const handle = await open(path, constants.O_RDONLY)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.nlink !== 1 || info.size > maxBytes
      || info.dev !== entry.dev || info.ino !== entry.ino) {
      throw failure('UNSAFE_ARTIFACT')
    }
    const bytes = await handle.readFile()
    if (bytes.length > maxBytes) throw failure('UNSAFE_ARTIFACT')
    if (await realpath(path) !== physical) throw failure('SOURCE_CHANGED')
    return bytes
  } finally { await handle.close() }
}

function validateName(name) {
  if (!SAFE_FILE.test(name) || name.endsWith('.') || name.endsWith(' ')
    || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/iu.test(name)) {
    throw failure('INVALID_ARTIFACT_NAME')
  }
}

/** Copy a settled run into an empty destination, leaving source bytes untouched.
 * The receipt describes copy integrity, not model or audit correctness.
 */
export async function copyTerminalEvidence({ sourceEvidenceRoot, targetEvidenceRoot, runId, workspaceId }) {
  if (!isAbsolute(sourceEvidenceRoot) || !isAbsolute(targetEvidenceRoot)
    || !RUN_ID.test(runId) || typeof workspaceId !== 'string' || !workspaceId) {
    throw failure('INVALID_INPUT')
  }
  const sourceRoot = await realpath(sourceEvidenceRoot)
  const targetRoot = await realpath(targetEvidenceRoot)
  if (within(sourceRoot, targetRoot) || within(targetRoot, sourceRoot)) throw failure('ROOTS_OVERLAP')
  if (!(await stat(targetRoot)).isDirectory()) throw failure('INVALID_TARGET')
  const sourceParentInfo = await lstat(join(sourceRoot, 'dsh-runtime'))
  const sourceRunInfo = await lstat(join(sourceRoot, 'dsh-runtime', runId))
  if (!sourceParentInfo.isDirectory() || sourceParentInfo.isSymbolicLink()
    || !sourceRunInfo.isDirectory() || sourceRunInfo.isSymbolicLink()) {
    throw failure('UNSAFE_SOURCE_RUN')
  }
  const sourceRun = await realpath(join(sourceRoot, 'dsh-runtime', runId))
  if (!within(sourceRoot, sourceRun) || basename(sourceRun) !== runId) throw failure('UNSAFE_SOURCE_RUN')
  const topNames = await readdir(sourceRun)
  if (topNames.length < 3 || topNames.length > MAX_FILES
    || !topNames.includes('evidence-manifest.v1.json') || !topNames.includes('diff.patch')
    || !topNames.includes('run-state.json') || topNames.includes('evidence-relocation.v1.json')) {
    throw failure('INVALID_SOURCE_RUN')
  }
  const sourceNames = []
  for (const name of topNames) {
    validateName(name)
    const info = await lstat(join(sourceRun, name))
    if (info.isFile() && !info.isSymbolicLink()) { sourceNames.push(name); continue }
    if (!info.isDirectory() || info.isSymbolicLink() || name !== `safe-trace-${runId}`) {
      throw failure('UNSAFE_ARTIFACT')
    }
    const physical = await realpath(join(sourceRun, name))
    if (!within(sourceRun, physical) || basename(physical) !== name) throw failure('UNSAFE_ARTIFACT')
    const children = await readdir(physical)
    if (children.length === 0) throw failure('INVALID_SOURCE_RUN')
    for (const child of children) {
      validateName(child)
      sourceNames.push(`${name}/${child}`)
    }
  }
  if (sourceNames.length > MAX_FILES) throw failure('INVALID_SOURCE_RUN')
  const artifacts = new Map()
  let totalBytes = 0
  for (const name of [...sourceNames].sort()) {
    const max = name === 'evidence-manifest.v1.json' ? MAX_MANIFEST_BYTES
      : name === 'diff.patch' ? MAX_DIFF_BYTES : MAX_FILE_BYTES
    const bytes = await readBoundedFile(sourceRun, name, max)
    totalBytes += bytes.length
    if (totalBytes > MAX_TOTAL_BYTES) throw failure('SOURCE_TOO_LARGE')
    artifacts.set(name, bytes)
  }
  const manifest = JSON.parse(artifacts.get('evidence-manifest.v1.json').toString('utf8'))
  const ref = manifest?.workspace_changes?.diff_content_ref
  if (manifest?.schema_version !== '1' || manifest.run_id !== runId
    || manifest.workspace_id !== workspaceId || typeof ref !== 'string' || !isAbsolute(ref)
    || await realpath(ref) !== join(sourceRun, 'diff.patch')) throw failure('SOURCE_IDENTITY_MISMATCH')
  const state = JSON.parse(artifacts.get('run-state.json').toString('utf8'))
  if (state?.schema_version !== 1 || state.run_id !== runId || state.workspace_id !== workspaceId
    || state.phase !== 'settled' || state.manifest_available !== true) throw failure('SOURCE_NOT_SETTLED')
  const copiedArtifacts = [...artifacts].map(([name, bytes]) => ({ name, size: bytes.length, sha256: hash(bytes) }))
  const receipt = {
    schema_version: 1, run_id: runId, workspace_id: workspaceId,
    source_diff_content_ref: ref,
    manifest_sha256: hash(artifacts.get('evidence-manifest.v1.json')),
    diff_sha256: hash(artifacts.get('diff.patch')),
    source_run_fingerprint: hash(Buffer.from(JSON.stringify(copiedArtifacts))),
    copied_artifacts: copiedArtifacts,
    created_at: new Date().toISOString(),
  }
  const destinationParent = join(targetRoot, 'dsh-runtime')
  try { await mkdir(destinationParent) } catch (error) { if (error?.code !== 'EEXIST') throw error }
  const physicalParent = await realpath(destinationParent)
  const parentInfo = await lstat(destinationParent)
  if (!parentInfo.isDirectory() || parentInfo.isSymbolicLink()
    || !within(targetRoot, physicalParent) || basename(physicalParent) !== 'dsh-runtime') {
    throw failure('UNSAFE_TARGET_PARENT')
  }
  const destinationRun = join(destinationParent, runId)
  try { await lstat(destinationRun); throw failure('TARGET_EXISTS') }
  catch (error) { if (error?.code !== 'ENOENT') throw error }
  const staging = join(destinationParent, `.dsh-evidence-copy-${randomUUID()}`)
  await mkdir(staging)
  for (const [name, bytes] of artifacts) {
    const target = join(staging, ...name.split('/'))
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, bytes, { flag: 'wx' })
  }
  await writeFile(join(staging, 'evidence-relocation.v1.json'), `${JSON.stringify(receipt)}\n`, { flag: 'wx' })
  for (const item of copiedArtifacts) {
    const copied = await readBoundedFile(staging, item.name, MAX_FILE_BYTES)
    if (copied.length !== item.size || hash(copied) !== item.sha256) throw failure('COPY_MISMATCH')
  }
  // Windows refuses a directory rename when the destination already exists.
  await rename(staging, destinationRun)
  return { status: 'COPIED', runId, artifactCount: copiedArtifacts.length,
    sourceRunFingerprint: receipt.source_run_fingerprint }
}

if (process.argv[1] && import.meta.url === pathToFileURL(await realpath(process.argv[1])).href) {
  const args = process.argv.slice(2)
  const flags = ['--source-evidence-root', '--target-evidence-root', '--run-id', '--workspace-id']
  const selected = Object.fromEntries(flags.map(flag => [flag, args[args.indexOf(flag) + 1]]))
  if (args.length !== 8 || flags.some(flag => !args.includes(flag) || !selected[flag]
    || selected[flag].startsWith('--'))) {
    process.stdout.write('{"status":"INVALID_INPUT"}\n')
    process.exitCode = 1
  } else {
    try {
      const result = await copyTerminalEvidence({ sourceEvidenceRoot: selected['--source-evidence-root'],
        targetEvidenceRoot: selected['--target-evidence-root'], runId: selected['--run-id'],
        workspaceId: selected['--workspace-id'] })
      process.stdout.write(`${JSON.stringify(result)}\n`)
    } catch (error) {
      process.stdout.write(`${JSON.stringify({ status: error?.code ?? 'COPY_FAILED' })}\n`)
      process.exitCode = 1
    }
  }
}
