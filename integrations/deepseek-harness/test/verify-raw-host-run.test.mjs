import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { verifyRawHostRun } from '../scripts/verify-raw-host-run.mjs'

const runId = 'dsh-runtime-11111111-2222-3333-4444-555555555555'
const sessionId = 'session-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
const worker = 'codex-safe-worker-11111111111111111111111111111111.jsonl'
const reviewer = 'api-agent-safe-role-22222222222222222222222222222222.jsonl'

async function fixture(change = () => {}) {
  const base = await mkdtemp(join(tmpdir(), 'raw-host-run-'))
  const runDir = join(base, runId)
  const traceDir = join(runDir, `safe-trace-${runId}`)
  await mkdir(traceDir, { recursive: true })
  const manifest = {
    schema_version: '1', run_id: runId, workspace_id: sessionId,
    task_kind: 'repository_change', status: 'completed', exit_code: 0,
    verification: { verdict: 'PASS' },
    audit: { status: 'settled', call_id: 'call-1', call_trace_path: `C:\\old\\${runId}-runtime-call-trace.jsonl` },
    execution_trajectory: { status: 'available', trace_complete: true, trace_file: `C:\\old\\${worker}` },
    review_trajectory: { status: 'available', trace_complete: true, trace_file: `C:\\old\\${reviewer}` },
    workspace_changes: { patch_complete: true, patch_applicable: true, diff_content_ref: 'C:\\old\\diff.patch', added_files: ['target.txt'], modified_files: [], deleted_files: [], file_metadata: [{ path: 'target.txt', afterBytes: 3, afterSha256: createHash('sha256').update('OK\n').digest('hex') }] },
  }
  const audit = { record: { session_id: sessionId, gate_decision: { outcome: 'ALLOW', proposal: { task_kind: 'repository_change' } } } }
  change({ manifest, audit })
  await writeFile(join(runDir, 'evidence-manifest.v1.json'), JSON.stringify(manifest))
  await writeFile(join(runDir, 'run-state.json'), JSON.stringify({ schema_version: 1, run_id: runId, workspace_id: sessionId, phase: 'settled', manifest_available: true }))
  await writeFile(join(runDir, 'diff.patch'), '--- /dev/null\n+++ b/target.txt\n@@ -0,0 +1 @@\n+OK\n')
  await writeFile(join(runDir, `${runId}-runtime-call-trace.jsonl`), JSON.stringify({ event: 'call_terminal', call_id: 'call-1', task_status: 'completed', runtime_exit_code: 0 }) + '\n')
  for (const [name, id] of [[worker, '1'.repeat(32)], [reviewer, '2'.repeat(32)]]) {
    const trace = '{"event":"terminal"}\n'
    await writeFile(join(traceDir, name), trace)
    await writeFile(join(traceDir, `${name}.closed`), JSON.stringify({ schema_version: 1, run_id: runId, trace_id: id, final_bytes: Buffer.byteLength(trace) }))
  }
  const auditFile = join(base, 'governance.jsonl')
  await writeFile(auditFile, JSON.stringify(audit) + '\n')
  const targetFile = join(base, 'target.txt')
  await writeFile(targetFile, 'OK\n')
  return { runDir, auditFile, traceDir, targetFile }
}

test('accepts a correlated terminal run without reading model text', async () => {
  const input = await fixture()
  const result = await verifyRawHostRun(input)
  assert.equal(result.status, 'RAW_EVIDENCE_CONSISTENT')
  assert.equal(result.audit_allow_records, 1)
  assert.equal(result.execution_trace.bytes, 21)
  assert.equal(result.target_file_verified, true)
})

test('accepts the CodeBuddy worker trace shape used by the second-device kit', async () => {
  const codebuddy = worker.replace('codex-safe-worker', 'codebuddy-safe-worker')
  const input = await fixture(({ manifest }) => { manifest.execution_trajectory.trace_file = `C:\\old\\${codebuddy}` })
  const { rename } = await import('node:fs/promises')
  await rename(join(input.traceDir, worker), join(input.traceDir, codebuddy))
  await rename(join(input.traceDir, `${worker}.closed`), join(input.traceDir, `${codebuddy}.closed`))
  assert.equal((await verifyRawHostRun(input)).status, 'RAW_EVIDENCE_CONSISTENT')
})

test('rejects a reviewer verdict that is not PASS', async () => {
  const input = await fixture(({ manifest }) => { manifest.verification.verdict = 'FAIL' })
  await assert.rejects(verifyRawHostRun(input), { code: 'TERMINAL_MISMATCH' })
})

test('rejects a mismatched review closure byte count', async () => {
  const input = await fixture()
  await writeFile(join(input.traceDir, `${reviewer}.closed`), JSON.stringify({ schema_version: 1, run_id: runId, trace_id: '2'.repeat(32), final_bytes: 1 }))
  await assert.rejects(verifyRawHostRun(input), { code: 'TRACE_CLOSURE_MISMATCH' })
})

test('rejects audit records for a different session', async () => {
  const input = await fixture(({ audit }) => { audit.record.session_id = 'session-other' })
  await assert.rejects(verifyRawHostRun(input), { code: 'AUDIT_NOT_MATCHED' })
})

test('rejects changed target bytes even when the Manifest still says PASS', async () => {
  const input = await fixture()
  await writeFile(input.targetFile, 'NO\n')
  await assert.rejects(verifyRawHostRun(input), { code: 'TARGET_BYTES_MISMATCH' })
})

test('rejects incomplete workspace patch despite terminal PASS', async () => {
  const input = await fixture(({ manifest }) => { manifest.workspace_changes.patch_complete = false })
  await assert.rejects(verifyRawHostRun(input), { code: 'CHANGE_SCOPE_MISMATCH' })
})
