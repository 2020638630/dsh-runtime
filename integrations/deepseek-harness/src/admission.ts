/** The final fail-closed boundary immediately before any Runtime process start. */
import type { Session } from '@deepseek-ai/dsh-session'
import type { GovernanceBridge, GovernedRoute } from './governance/bridge.ts'

type Evaluator = Pick<GovernanceBridge, 'evaluatePreStart'>

/** Evaluate once, then launch once only on an explicit eligible decision. */
export async function startGoverned<T>(
  evaluator: Evaluator,
  session: Session,
  callerId: string,
  route: GovernedRoute,
  signal: AbortSignal,
  launch: () => Promise<T> | T,
): Promise<T> {
  signal.throwIfAborted()
  const decision = await evaluator.evaluatePreStart(session, callerId, route)
  signal.throwIfAborted()
  if (decision.kind !== 'EXECUTION_ELIGIBLE') {
    throw new Error(`dsh runtime governance denied start (${decision.kind})`)
  }
  return launch()
}
