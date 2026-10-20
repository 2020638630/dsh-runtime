/** Strict JSONL wire types and response validation for the governance worker. */
import { z } from 'zod'
/** Version of the Host/worker governance protocol. */
export const GOVERNANCE_PROTOCOL_VERSION = '1' as const
/** Exact policy identity returned by the governance worker. */
export interface PolicyIdentity {
  readonly policy_id: string
  readonly policy_version: string
  readonly artifact_schema_version: string
  readonly policy_hash: string
}
/** Strict schema shared by the governance wire and the Host's durable pin. */
export const policyIdentitySchema: z.ZodType<PolicyIdentity> = z.object({
  policy_id: z.string().min(1),
  policy_version: z.string().min(1),
  artifact_schema_version: z.string().min(1),
  policy_hash: z.string().regex(/^[0-9a-f]{64}$/u),
}).strict()
/** First request that initializes one worker lifetime. */
export interface InitializeRequest {
  readonly kind: 'INITIALIZE'
  readonly protocol_version: typeof GOVERNANCE_PROTOCOL_VERSION
  readonly policy_source: string
  readonly expected_policy_hash: string
  readonly enabled_workloads: readonly string[]
  readonly audit_path: string
}
/** Request that creates or resumes one pinned Session binding. */
export interface BindSessionRequest {
  readonly kind: 'BIND_SESSION'
  readonly request_id: string
  readonly session_id: string
  readonly mode: 'create' | 'resume'
  readonly pinned_policy_identity?: PolicyIdentity
}
/** Supported Host task kinds carried by the unchanged pre-start message. */
export type GovernedTaskKind = 'repository_change' | 'repository_inspection'
/** Supported Host reason codes paired with the task kinds above. */
export type GovernedReasonCode = 'host_v1_repository_change' | 'host_v2_repository_inspection'
/** Pre-start evaluation request with the existing wire shape and widened values. */
export interface EvaluatePreStartRequest {
  readonly kind: 'EVALUATE_PRE_START'
  readonly request_id: string
  readonly session_id: string
  readonly caller_id: string
  readonly pinned_policy_identity: PolicyIdentity
  readonly task_kind: GovernedTaskKind
  readonly reason_code: GovernedReasonCode
  readonly request_structure: {
    readonly request_type: 'subagent_one_shot_start'
    readonly required_fields: readonly [
      'parent',
      'prompt',
      'signal',
    ]
  }
}
const readySchema = z.object({ kind: z.literal('READY'), protocol_version: z.literal(GOVERNANCE_PROTOCOL_VERSION), policy_identity: policyIdentitySchema }).strict()
const boundSchema = z.object({ kind: z.literal('SESSION_BOUND'), request_id: z.string().min(1), session_id: z.string().min(1), policy_identity: policyIdentitySchema }).strict()
const decisionBase = { request_id: z.string().min(1), session_id: z.string().min(1), policy_identity: policyIdentitySchema, task_kind: z.union([z.literal('repository_change'), z.literal('repository_inspection')]) }
const eligibleSchema = z.object({ kind: z.literal('EXECUTION_ELIGIBLE'), ...decisionBase, reason_code: z.literal('execution_eligible') }).strict()
const blockedSchema = z.object({ kind: z.literal('BLOCKED'), ...decisionBase, reason_code: z.union([z.literal('gate_denied'), z.literal('audit_persistence_failed')]), gate_reason_code: z.string().min(1) }).strict()
const failureSchema = z.object({ kind: z.literal('FAILURE'), request_id: z.string().min(1).nullable(), reason_code: z.union([z.literal('initialization_failed'), z.literal('protocol_error'), z.literal('governance_failure'), z.literal('bridge_failure')]), diagnostic: z.string().min(1) }).strict()
/** Validated worker initialization response. */
export type ReadyResponse = z.infer<typeof readySchema>
/** Validated Session binding response. */
export type SessionBoundResponse = z.infer<typeof boundSchema>
/** Validated eligible or blocked governance decision. */
export type GovernanceDecision = z.infer<typeof eligibleSchema> | z.infer<typeof blockedSchema>
/** Validated failure when governance cannot authorize execution. */
export type GovernanceFailure = z.infer<typeof failureSchema>
/** All validated non-initialization worker responses. */
export type OperationalResponse = SessionBoundResponse | GovernanceDecision | GovernanceFailure
const operationalSchema = z.discriminatedUnion('kind', [boundSchema, eligibleSchema, blockedSchema, failureSchema])
/** Parse one worker stdout line as a strict response envelope.
 * @param line - one complete worker output line.
 * @returns the validated response envelope.
 */
export function parseWorkerResponse(line: string): ReadyResponse | OperationalResponse {
  let value: unknown
  try {
    value = JSON.parse(line)
  }
  catch (error) {
    throw new Error('governance bridge received malformed JSON', { cause: error })
  }
  const ready = readySchema.safeParse(value)
  if (ready.success)
    return ready.data
  const operational = operationalSchema.safeParse(value)
  if (operational.success)
    return operational.data
  throw new Error('governance bridge received an unknown response shape')
}
/** Encode exactly one compact JSONL request.
 * @param request - the request to encode.
 * @returns one newline-terminated JSONL record.
 */
export function encodeWorkerRequest(request: InitializeRequest | BindSessionRequest | EvaluatePreStartRequest): string { return `${JSON.stringify(request)}\n` }
/** Build the only safe local result when no authoritative worker result exists.
 * @param requestId - the request id that remains attributable, or null.
 * @returns a fail-closed bridge failure response.
 */
export function bridgeFailure(requestId: string | null): GovernanceFailure { return { kind: 'FAILURE', request_id: requestId, reason_code: 'bridge_failure', diagnostic: 'governance worker response unavailable' } }
