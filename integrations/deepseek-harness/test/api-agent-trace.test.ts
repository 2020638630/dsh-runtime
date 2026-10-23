import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { inspectApiAgentTrace } from '../src/runtime/api-agent-trace-evidence.ts'
import { writeTerminalEvidence } from '../src/runtime/evidence-manifest.ts'
import { captureWorkspace } from '../src/runtime/workspace-evidence.ts'

const RUN_ID = 'dsh-runtime-00000000-0000-4000-8000-000000000005'
const TRACE_ID = 'a'.repeat(32)

function fixture(
  roleName: 'inspector' | 'reviewer' = 'inspector',
  terminalReason: 'completed' | 'failed' | 'cancelled' = 'completed',
) {
  const root = mkdtempSync(join(tmpdir(), 'dsh-api-agent-trace-'))
  const runDir = join(root, RUN_ID)
  mkdirSync(runDir)
  const traceDir = join(runDir, `safe-trace-${RUN_ID}`)
  mkdirSync(traceDir)
  const tracePath = join(traceDir, `api-agent-safe-role-${TRACE_ID}.jsonl`)
  const base = {
    schema_version: 1, trace_id: TRACE_ID,
    captured_at_utc: '2026-10-23T00:00:00+00:00', role_name: roleName,
  }
  const records = [
    { ...base, event_seq: 0, event_type: 'started', tool_name: null,
      tool_status: null, terminal_reason: null },
    { ...base, event_seq: 1, event_type: 'tool_call', tool_name: 'read_file',
      tool_status: 'completed', terminal_reason: null },
    { ...base, event_seq: 2, event_type: 'terminal', tool_name: null,
      tool_status: null, terminal_reason: terminalReason },
  ]
  const bytes = Buffer.from(records.map(event => JSON.stringify(event)).join('\n') + '\n')
  writeFileSync(tracePath, bytes)
  writeFileSync(`${tracePath}.closed`, JSON.stringify({
    schema_version: 1, run_id: RUN_ID, trace_id: TRACE_ID, final_bytes: bytes.length,
  }) + '\n')
  return { traceDir, tracePath }
}

test('API Agent trace reader returns only bounded metadata after closure', async () => {
  const { traceDir, tracePath } = fixture()
  const evidence = await inspectApiAgentTrace({
    runId: RUN_ID, traceDir, tracePath, processExited: true,
  })
  assert.deepEqual(evidence, {
    status: 'available', traceComplete: true, traceId: TRACE_ID,
    roleName: 'inspector', terminalReason: 'completed',
    toolOperationsSummary: { list_files: 0, read_file: 1, search_text: 0 },
  })
})

test('API Agent trace reader rejects a mismatched closure marker', async () => {
  const { traceDir, tracePath } = fixture()
  writeFileSync(`${tracePath}.closed`, JSON.stringify({
    schema_version: 1, run_id: RUN_ID, trace_id: TRACE_ID, final_bytes: 1,
  }) + '\n')
  const evidence = await inspectApiAgentTrace({
    runId: RUN_ID, traceDir, tracePath, processExited: true,
  })
  assert.equal(evidence.status, 'incomplete')
  assert.equal(evidence.traceComplete, false)
})

test('API Agent trace remains unknown before child exit', async () => {
  const { traceDir, tracePath } = fixture()
  const evidence = await inspectApiAgentTrace({
    runId: RUN_ID, traceDir, tracePath, processExited: false,
  })
  assert.equal(evidence.status, 'unknown')
})

test('inspection Manifest uses API Agent trace source when a closed trace exists', async () => {
  const { traceDir } = fixture()
  const runDir = join(traceDir, '..')
  const workspace = mkdtempSync(join(tmpdir(), 'dsh-api-agent-workspace-'))
  execFileSync('git', ['init', '-q', workspace])
  writeFileSync(join(workspace, 'README.md'), 'isolated inspection\n')
  const before = await captureWorkspace(workspace)
  const task = {
    task_id: '00000000-0000-4000-8000-000000000006',
    task_kind: 'repository_inspection', workspace_id: 'api.fixture',
    status: 'completed', iteration: 1, result: 'done', error: null,
    last_invocation_result: 'done',
  }
  await writeTerminalEvidence({
    runId: RUN_ID, runDir, safeTraceDir: traceDir,
    callTracePath: join(runDir, `${RUN_ID}-runtime-call-trace.jsonl`),
    workspace, workspaceId: 'api.fixture', before,
    taskKind: 'repository_inspection', task, exitCode: 0,
    durationMs: 1, stdout: '{}\n', maxTurnsConfig: null,
  })
  const manifest = JSON.parse(readFileSync(join(runDir, 'evidence-manifest.v1.json'), 'utf8'))
  assert.equal(manifest.execution_trajectory.source, 'api_agent_safe_event_trace')
  assert.equal(manifest.execution_trajectory.status, 'available')
  assert.equal(manifest.execution_trajectory.trace_complete, true)
  assert.deepEqual(manifest.execution_trajectory.tool_operations_summary,
    { list_files: 0, read_file: 1, search_text: 0 })
  assert.deepEqual(manifest.workspace_changes.modified_files, [])
})

test('inspection Manifest marks missing expected API trace unavailable', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-api-agent-missing-'))
  const runDir = join(root, RUN_ID)
  const traceDir = join(runDir, `safe-trace-${RUN_ID}`)
  mkdirSync(traceDir, { recursive: true })
  const workspace = mkdtempSync(join(tmpdir(), 'dsh-api-agent-workspace-'))
  execFileSync('git', ['init', '-q', workspace])
  writeFileSync(join(workspace, 'README.md'), 'isolated inspection\n')
  const before = await captureWorkspace(workspace)
  await writeTerminalEvidence({
    runId: RUN_ID, runDir, safeTraceDir: traceDir,
    callTracePath: join(runDir, `${RUN_ID}-runtime-call-trace.jsonl`),
    workspace, workspaceId: 'api.fixture', before,
    taskKind: 'repository_inspection',
    task: {
      task_id: '00000000-0000-4000-8000-000000000007',
      task_kind: 'repository_inspection', workspace_id: 'api.fixture',
      status: 'failed', iteration: 0, result: null, error: 'preflight failed',
      last_invocation_result: null,
    },
    exitCode: 0, durationMs: 1, stdout: '{}\n', maxTurnsConfig: null,
    expectedApiInspector: true,
  })
  const manifest = JSON.parse(readFileSync(join(runDir, 'evidence-manifest.v1.json'), 'utf8'))
  assert.equal(manifest.execution_trajectory.source, 'api_agent_safe_event_trace')
  assert.equal(manifest.execution_trajectory.status, 'unavailable')
})

test('inspection Manifest rejects a reviewer trace in the same run', async () => {
  const { traceDir } = fixture('reviewer')
  const runDir = join(traceDir, '..')
  const workspace = mkdtempSync(join(tmpdir(), 'dsh-api-role-mismatch-'))
  execFileSync('git', ['init', '-q', workspace])
  writeFileSync(join(workspace, 'README.md'), 'isolated inspection\n')
  const before = await captureWorkspace(workspace)
  await writeTerminalEvidence({
    runId: RUN_ID, runDir, safeTraceDir: traceDir,
    callTracePath: join(runDir, `${RUN_ID}-runtime-call-trace.jsonl`),
    workspace, workspaceId: 'api.fixture', before,
    taskKind: 'repository_inspection',
    task: {
      task_id: '00000000-0000-4000-8000-000000000009',
      task_kind: 'repository_inspection', workspace_id: 'api.fixture',
      status: 'completed', iteration: 1, result: 'done', error: null,
      last_invocation_result: 'done',
    },
    exitCode: 0, durationMs: 1, stdout: '{}\n', maxTurnsConfig: null,
    expectedApiInspector: true,
  })
  const manifest = JSON.parse(readFileSync(join(runDir, 'evidence-manifest.v1.json'), 'utf8'))
  assert.equal(manifest.execution_trajectory.status, 'incomplete')
  assert.equal(manifest.execution_trajectory.trace_complete, false)
})

async function changeManifest(
  traceDir: string, iteration = 2, expectedWorkerAdapter: 'codebuddy' | 'codex' = 'codebuddy',
) {
  const runDir = join(traceDir, '..')
  const workspace = mkdtempSync(join(tmpdir(), 'dsh-api-review-workspace-'))
  execFileSync('git', ['init', '-q', workspace])
  writeFileSync(join(workspace, 'README.md'), 'isolated review\n')
  const before = await captureWorkspace(workspace)
  await writeTerminalEvidence({
    runId: RUN_ID, runDir, safeTraceDir: traceDir,
    callTracePath: join(runDir, `${RUN_ID}-runtime-call-trace.jsonl`),
    workspace, workspaceId: 'api.review.fixture', before,
    taskKind: 'repository_change',
    task: {
      task_id: '00000000-0000-4000-8000-000000000008',
      task_kind: 'repository_change', workspace_id: 'api.review.fixture',
      status: iteration === 2 ? 'completed' : 'failed', iteration,
      result: iteration === 2 ? 'done' : null,
      error: iteration === 2 ? null : 'worker failed',
      last_invocation_result: iteration === 2 ? 'checked\nDSH_VERIFICATION: PASS' : null,
    },
    exitCode: 0, durationMs: 1, stdout: '{}\n', maxTurnsConfig: 12,
    expectedApiReviewer: true,
    expectedWorkerAdapter,
  })
  return JSON.parse(readFileSync(join(runDir, 'evidence-manifest.v1.json'), 'utf8'))
}

test('API reviewer trace is separate from worker trace and Codex attribution', async () => {
  const { traceDir } = fixture('reviewer')
  const manifest = await changeManifest(traceDir)
  assert.equal(manifest.execution_trajectory.source, 'safe_event_trace')
  assert.equal(manifest.execution_trajectory.status, 'unavailable')
  assert.equal(manifest.review_trajectory.source, 'api_agent_safe_event_trace')
  assert.equal(manifest.review_trajectory.status, 'available')
  assert.equal(manifest.review_trajectory.role_name, 'reviewer')
  assert.equal(manifest.review_trajectory.terminal_reason, 'completed')
  assert.equal(manifest.review_trajectory.tool_operations_summary.read_file, 1)
  assert.equal(manifest.authority_phases.phase_2_codex_effective_write, null)
  assert.equal(manifest.authority_phases.phase_2_api_agent_effective_write, false)
  assert.equal(manifest.authority_phases.phase_1_codebuddy_effective_write, true)
  assert.equal(manifest.authority_phases.phase_1_codex_effective_write, null)
  assert.equal(manifest.verification.verdict, 'PASS')
})

test('Codex worker is not attributed to CodeBuddy in an API review task', async () => {
  const { traceDir } = fixture('reviewer')
  const manifest = await changeManifest(traceDir, 2, 'codex')
  assert.equal(manifest.authority_phases.phase_1_codebuddy_effective_write, null)
  assert.equal(manifest.authority_phases.phase_1_codex_effective_write, true)
  assert.equal(manifest.authority_phases.phase_2_codex_effective_write, null)
  assert.equal(manifest.review_trajectory.status, 'available')
})

test('API reviewer trace rejects inspector role rather than misattributing it', async () => {
  const { traceDir } = fixture('inspector')
  const manifest = await changeManifest(traceDir)
  assert.equal(manifest.review_trajectory.status, 'incomplete')
  assert.equal(manifest.review_trajectory.role_name, null)
  assert.equal(manifest.review_trajectory.tool_operations_summary, null)
  assert.equal(manifest.verification.verdict, 'UNAVAILABLE')
})

test('expected API reviewer without trace is unavailable', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-api-review-missing-'))
  const traceDir = join(root, RUN_ID, `safe-trace-${RUN_ID}`)
  mkdirSync(traceDir, { recursive: true })
  const manifest = await changeManifest(traceDir)
  assert.equal(manifest.review_trajectory.status, 'unavailable')
  assert.equal(manifest.review_trajectory.trace_file, null)
  assert.equal(manifest.authority_phases.phase_2_codex_effective_write, null)
  assert.equal(manifest.verification.verdict, 'UNAVAILABLE')
})

test('failed reviewer trace cannot substantiate a PASS verdict', async () => {
  const { traceDir } = fixture('reviewer', 'failed')
  const manifest = await changeManifest(traceDir)
  assert.equal(manifest.review_trajectory.status, 'available')
  assert.equal(manifest.review_trajectory.terminal_reason, 'failed')
  assert.equal(manifest.verification.verdict, 'UNAVAILABLE')
})

test('cancelled reviewer trace cannot substantiate a PASS verdict', async () => {
  const { traceDir } = fixture('reviewer', 'cancelled')
  const manifest = await changeManifest(traceDir)
  assert.equal(manifest.review_trajectory.terminal_reason, 'cancelled')
  assert.equal(manifest.verification.verdict, 'UNAVAILABLE')
})

test('configured API reviewer is not marked missing when worker failed first', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-api-review-not-run-'))
  const traceDir = join(root, RUN_ID, `safe-trace-${RUN_ID}`)
  mkdirSync(traceDir, { recursive: true })
  const manifest = await changeManifest(traceDir, 1)
  assert.equal(manifest.review_trajectory.status, 'not_applicable')
  assert.equal(manifest.authority_phases.phase_2_codex_effective_write, null)
  assert.equal(manifest.authority_phases.phase_2_api_agent_effective_write, null)
})
