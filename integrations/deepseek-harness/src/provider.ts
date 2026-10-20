/** Two fixed-purpose official Subagent providers, each governed at its own start boundary. */
import { NO_START_CAPABILITIES } from '@deepseek-ai/dsh-subagent'
import type { ResolvedSubagentStartRequest, SubagentProvider, SubagentRun } from '@deepseek-ai/dsh-subagent'
import { startGoverned } from './admission.ts'
import type { GovernanceBridge, GovernedRoute } from './governance/bridge.ts'

export const RUNTIME_ROUTES = Object.freeze({
  repository_inspection: { taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection' },
  repository_change: { taskKind: 'repository_change', reasonCode: 'host_v1_repository_change' },
} as const satisfies Record<string, GovernedRoute>)

export const RUNTIME_PROVIDER_NAMES = Object.freeze({
  repository_inspection: 'dsh-runtime-inspection',
  repository_change: 'dsh-runtime-change',
} as const)

export type RuntimeTaskKind = keyof typeof RUNTIME_ROUTES
type RuntimeLauncher = (request: ResolvedSubagentStartRequest, taskKind: RuntimeTaskKind) => Promise<SubagentRun>
type Evaluator = Pick<GovernanceBridge, 'evaluatePreStart'>

/** A direct Host start reaches governance even when no dedicated tool initiated it. */
export function createGovernedProvider(
  taskKind: RuntimeTaskKind,
  evaluator: Evaluator,
  launch: RuntimeLauncher,
): SubagentProvider {
  const route = RUNTIME_ROUTES[taskKind]
  return {
    name: RUNTIME_PROVIDER_NAMES[taskKind],
    capabilities: NO_START_CAPABILITIES,
    inheritsParentContext: false,
    async start(request) {
      return startGoverned(evaluator, request.parent.session, String(request.parent.id), route, request.signal, () => launch(request, taskKind))
    },
  }
}
