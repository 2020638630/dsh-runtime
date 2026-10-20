/** Host-only durable storage for the exact worker-returned governance identity. */
import type { Session } from '@deepseek-ai/dsh-session'
import type SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import type { ProjectionDefinition } from '@deepseek-ai/dsh-session-projection'
import { policyIdentitySchema, type PolicyIdentity } from './protocol.ts'
declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /** Records the exact policy identity returned by the worker for this Session.
     * @param data - immutable policy identity pinned after the first bind.
 */
    'subagent/governance-policy-pin': PolicyIdentity
  }
}
declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {
    subagentGovernancePolicyPin: PolicyIdentity | null
  }
}
const pinSchema = policyIdentitySchema.nullable()

function sameIdentity(left: PolicyIdentity, right: PolicyIdentity): boolean {
  return left.policy_id === right.policy_id
    && left.policy_version === right.policy_version
    && left.artifact_schema_version === right.artifact_schema_version
    && left.policy_hash === right.policy_hash
}

/** Host-only fold: the first pin wins; a conflicting later event fails replay closed. */
export const governancePolicyPinProjectionDefinition = {
  key: 'subagentGovernancePolicyPin',
  stateVersion: 1,
  stateSchema: pinSchema,
  init: () => null,
  apply: (pin, event) => {
    if (event.type !== 'subagent/governance-policy-pin') return pin
    const next = policyIdentitySchema.parse(event.data)
    if (pin === null) return next
    if (!sameIdentity(pin, next)) throw new Error('subagent governance policy pin is immutable')
    return pin
  },
} satisfies ProjectionDefinition<'subagentGovernancePolicyPin', PolicyIdentity | null>

/** Read a detached exact identity from the Host session projection.
 * @param projections - the Session projection registry.
 * @param session - the Session whose pin is read.
 * @returns the exact pinned identity, or undefined when absent.
 */
export function governancePolicyPin(
  projections: Pick<SessionProjectionRegistry, 'stateOf'>,
  session: Session,
): PolicyIdentity | undefined {
  const pin = projections.stateOf(session, 'subagentGovernancePolicyPin')
  return pin === null || pin === undefined ? undefined : { ...pin }
}

/** Append the worker-returned identity once; never replace a different pin.
 * @param projections - the Session projection registry.
 * @param session - the Session receiving the pin event.
 * @param identity - the exact worker-returned policy identity.
 */
export function recordGovernancePolicyPin(
  projections: Pick<SessionProjectionRegistry, 'stateOf'>,
  session: Session,
  identity: PolicyIdentity,
): void {
  const validated = policyIdentitySchema.parse(identity)
  const current = governancePolicyPin(projections, session)
  if (current !== undefined) {
    if (!sameIdentity(current, validated)) {
      throw new Error('subagent governance session already has a different policy pin')
    }
    return
  }
  session.append('subagent/governance-policy-pin', { ...validated })
}
