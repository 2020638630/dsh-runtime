#!/usr/bin/env node
/** Read-only consistency check for one copied Windows Host Runtime run. */
import { createHash } from 'node:crypto'
import { constants } from 'node:fs'
import { lstat, open, realpath } from 'node:fs/promises'
import { basename, dirname, isAbsolute, join, relative, sep, win32 } from 'node:path'
import { pathToFileURL } from 'node:url'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const TRACE_NAMES = {
  execution_trajectory: /^(?:codex|codebuddy)-safe-worker-([0-9a-f]{32})\.jsonl$/u,
  review_trajectory: /^api-agent-safe-role-([0-9a-f]{32})\.jsonl$/u,
}
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')
const fail = code => { const error = new Error(code); error.code = code; throw error }

function inside(root, child) {
  const rel = relative(root, child)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

async function boundedFile(file, root, maxBytes) {
  const before = await lstat(file)
  if (!before.isFile() || before.isSymbolicLink() || before.nlink !== 1 || before.size > maxBytes) fail('UNSAFE_FILE')
  const physical = await realpath(file)
  if (!inside(root, physical)) fail('PATH_ESCAPE')
  const handle = await open(file, constants.O_RDONLY)
  try {
    const opened = await handle.stat()
    if (!opened.isFile() || opened.nlink !== 1 || opened.size > maxBytes
      || opened.dev !== before.dev || opened.ino !== before.ino) fail('SOURCE_CHANGED')
    const bytes = await handle.readFile()
    const after = await handle.stat()
    if (bytes.length > maxBytes || after.size !== opened.size || after.mtimeMs !== opened.mtimeMs
      || await realpath(file) !== physical) fail('SOURCE_CHANGED')
    return bytes
  } finally { await handle.close() }
}

function json(bytes) {
  try { return JSON.parse(bytes.toString('utf8')) } catch { fail('INVALID_JSON') }
}

function lines(bytes) {
  const rows = bytes.toString('utf8').split(/\r?\n/u).filter(Boolean)
  if (rows.length > 1000) fail('TOO_MANY_RECORDS')
  return rows.map(row => json(Buffer.from(row)))
}

function referencedName(ref, pattern) {
  if (typeof ref !== 'string' || !win32.isAbsolute(ref)) fail('INVALID_REFERENCE')
  const name = win32.basename(ref)
  if (!pattern.test(name)) fail('INVALID_REFERENCE')
  return name
}

/** A consistent copied evidence chain is not a signature or a release verdict. */
export async function verifyRawHostRun({ runDir, auditFile, targetFile }) {
  if (!isAbsolute(runDir) || !isAbsolute(auditFile) || !RUN_ID.test(basename(runDir))) fail('INVALID_INPUT')
  if (targetFile !== undefined && !isAbsolute(targetFile)) fail('INVALID_INPUT')
  const runEntry = await lstat(runDir)
  if (!runEntry.isDirectory() || runEntry.isSymbolicLink()) fail('UNSAFE_RUN_DIRECTORY')
  const root = await realpath(runDir)
  const runId = basename(root)
  if (!RUN_ID.test(runId)) fail('INVALID_RUN_ID')
  const manifestBytes = await boundedFile(join(root, 'evidence-manifest.v1.json'), root, 1_048_576)
  const manifest = json(manifestBytes)
  const state = json(await boundedFile(join(root, 'run-state.json'), root, 1_048_576))
  if (manifest.schema_version !== '1' || manifest.run_id !== runId || !manifest.workspace_id
    || manifest.task_kind !== 'repository_change'
    || manifest.status !== 'completed' || manifest.exit_code !== 0
    || manifest.verification?.verdict !== 'PASS'
    || manifest.audit?.status !== 'settled'
    || state.schema_version !== 1 || state.run_id !== runId
    || state.workspace_id !== manifest.workspace_id || state.phase !== 'settled'
    || state.manifest_available !== true) fail('TERMINAL_MISMATCH')

  const changes = manifest.workspace_changes
  if (changes?.patch_complete !== true || changes.patch_applicable !== true
    || changes.added_files?.length !== 1 || changes.modified_files?.length !== 0
    || changes.deleted_files?.length !== 0
    || referencedName(changes.diff_content_ref, /^diff\.patch$/u) !== 'diff.patch') {
    fail('CHANGE_SCOPE_MISMATCH')
  }
  const diff = await boundedFile(join(root, 'diff.patch'), root, 8 * 1_048_576)
  if (!diff.length) fail('DIFF_MISSING')

  const traceDir = join(root, `safe-trace-${runId}`)
  const traceEntry = await lstat(traceDir)
  if (!traceEntry.isDirectory() || traceEntry.isSymbolicLink()
    || !inside(root, await realpath(traceDir))) fail('UNSAFE_TRACE_DIRECTORY')
  const traces = {}
  for (const [role, namePattern] of Object.entries(TRACE_NAMES)) {
    const item = manifest[role]
    if (item?.status !== 'available' || item.trace_complete !== true) fail('TRACE_NOT_COMPLETE')
    const name = referencedName(item.trace_file, namePattern)
    const traceId = name.match(namePattern)[1]
    const trace = await boundedFile(join(traceDir, name), root, 32 * 1_048_576)
    const closed = json(await boundedFile(join(traceDir, `${name}.closed`), root, 4096))
    if (!trace.length || closed.schema_version !== 1 || closed.run_id !== runId
      || closed.trace_id !== traceId || closed.final_bytes !== trace.length) fail('TRACE_CLOSURE_MISMATCH')
    traces[role] = { bytes: trace.length, sha256: sha256(trace) }
  }

  const callName = referencedName(manifest.audit.call_trace_path,
    new RegExp(`^${runId}-runtime-call-trace\\.jsonl$`, 'u'))
  const calls = lines(await boundedFile(join(root, callName), root, 8 * 1_048_576))
  const terminals = calls.filter(row => row.event === 'call_terminal' && row.call_id === manifest.audit.call_id)
  if (terminals.length !== 1 || terminals[0].task_status !== 'completed'
    || terminals[0].runtime_exit_code !== 0) fail('CALL_TERMINAL_MISMATCH')
  const auditRoot = await realpath(dirname(auditFile))
  const audit = lines(await boundedFile(auditFile, auditRoot, 8 * 1_048_576))
  const allows = audit.filter(row => row.record?.session_id === manifest.workspace_id
    && row.record?.gate_decision?.outcome === 'ALLOW'
    && row.record?.gate_decision?.proposal?.task_kind === manifest.task_kind)
  if (!allows.length) fail('AUDIT_NOT_MATCHED')

  let target = null
  if (targetFile !== undefined) {
    const name = basename(targetFile)
    const metadata = changes?.file_metadata?.find(item => item.path === name)
    if (changes?.added_files?.length !== 1 || changes.added_files[0] !== name
      || !metadata || metadata.afterBytes === null || typeof metadata.afterSha256 !== 'string') {
      fail('TARGET_NOT_IN_MANIFEST')
    }
    const targetRoot = await realpath(dirname(targetFile))
    const bytes = await boundedFile(targetFile, targetRoot, 32 * 1_048_576)
    const digest = sha256(bytes)
    if (bytes.length !== metadata.afterBytes || digest !== metadata.afterSha256.toLowerCase()) fail('TARGET_BYTES_MISMATCH')
    target = { name, bytes: bytes.length, sha256: digest }
  }

  return {
    status: 'RAW_EVIDENCE_CONSISTENT', run_id: runId, task_kind: manifest.task_kind,
    task_status: manifest.status, reviewer_verdict: manifest.verification.verdict,
    workspace_id: manifest.workspace_id, manifest_sha256: sha256(manifestBytes),
    diff_sha256: sha256(diff), added_file: changes.added_files[0],
    execution_trace: traces.execution_trajectory, review_trace: traces.review_trajectory,
    audit_allow_records: allows.length, audit_linkage: 'session_and_task_kind_only',
    target_file_verified: target !== null, target,
    claim: `Copied records pass bounded consistency checks; governance audit has no run ID, so its ALLOW links by session and task kind only.${target ? '' : ' Target file bytes were not checked.'} No model-correctness or release claim.`,
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(await realpath(process.argv[1])).href) {
  const args = process.argv.slice(2)
  const allowed = new Set(['--run-dir', '--audit-file', '--target-file'])
  const pairs = []
  for (let i = 0; i < args.length; i += 2) pairs.push([args[i], args[i + 1]])
  const selected = Object.fromEntries(pairs)
  if (![4, 6].includes(args.length) || pairs.some(([flag, value]) => !allowed.has(flag) || !value)
    || Object.keys(selected).length !== pairs.length
    || !selected['--run-dir'] || !selected['--audit-file']) {
    process.stdout.write('{"status":"INVALID_INPUT"}\n')
    process.exitCode = 1
  } else {
    try { process.stdout.write(`${JSON.stringify(await verifyRawHostRun({ runDir: selected['--run-dir'], auditFile: selected['--audit-file'], targetFile: selected['--target-file'] }))}\n`) }
    catch (error) { process.stdout.write(`${JSON.stringify({ status: error?.code ?? 'VERIFY_FAILED' })}\n`); process.exitCode = 1 }
  }
}
