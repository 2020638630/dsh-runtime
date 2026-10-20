/** Adapt a governed official Subagent request to the existing Runtime one-shot transport. */
import { assertUsableCwd } from '@deepseek-ai/dsh-subagent'
import type { ResolvedSubagentStartRequest, SubagentRun } from '@deepseek-ai/dsh-subagent'
import type { SubprocessHandle, SubprocessSpawnSpec } from '@deepseek-ai/dsh-subprocess'
import { startDshRuntimeRun, type DshRuntimeRunSpec } from './runtime/run.ts'
import type { RuntimeTaskKind } from './provider.ts'

export interface RuntimeLauncherConfig {
  readonly runtimeRoot: string
  readonly python: string
  readonly env: Record<string, string>
  readonly evidenceRoot?: string
  readonly disposeGraceMs: number
  readonly spawn: (spec: SubprocessSpawnSpec) => SubprocessHandle
  readonly onError?: DshRuntimeRunSpec['onError']
  readonly onEvidenceError?: DshRuntimeRunSpec['onEvidenceError']
}

type StartRun = (request: ResolvedSubagentStartRequest, spec: DshRuntimeRunSpec) => Promise<SubagentRun>

/** The parent Session owns the workspace; a model-supplied child cwd never changes it. */
export function createRuntimeLauncher(config: RuntimeLauncherConfig, startRun: StartRun = startDshRuntimeRun) {
  return (request: ResolvedSubagentStartRequest, taskKind: RuntimeTaskKind): Promise<SubagentRun> => {
    request.signal.throwIfAborted()
    const parentCwd = request.parent.session.header.cwd
    if (parentCwd === undefined) throw new Error('dsh runtime: parent session has no workspace directory')
    const workspace = assertUsableCwd('dsh-runtime-plugin', 'parent session cwd', parentCwd)
    return startRun(request, {
      cwd: workspace,
      workspaceId: request.parent.session.id,
      taskKind,
      runtimeRoot: config.runtimeRoot,
      python: config.python,
      env: config.env,
      ...config.evidenceRoot === undefined ? {} : { evidenceRoot: config.evidenceRoot },
      disposeGraceMs: config.disposeGraceMs,
      spawn: config.spawn,
      ...config.onError === undefined ? {} : { onError: config.onError },
      ...config.onEvidenceError === undefined ? {} : { onEvidenceError: config.onEvidenceError },
    })
  }
}
