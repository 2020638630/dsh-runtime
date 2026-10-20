/** FIFO process transport and lazy session-pin orchestration. */
import { randomUUID } from 'node:crypto'
import { createInterface } from 'node:readline'
import type { Session } from '@deepseek-ai/dsh-session'
import type SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import type { SubprocessHandle, SubprocessSpawnSpec } from '@deepseek-ai/dsh-subprocess'
import { bridgeFailure, encodeWorkerRequest, GOVERNANCE_PROTOCOL_VERSION, parseWorkerResponse, type BindSessionRequest, type EvaluatePreStartRequest, type GovernanceDecision, type GovernanceFailure, type GovernedReasonCode, type GovernedTaskKind, type InitializeRequest, type OperationalResponse, type ReadyResponse } from './protocol.ts'
import { governancePolicyPin, recordGovernancePolicyPin } from './session-pin.ts'

/** Configuration for the managed Python governance worker and its audit inputs. */
export interface BridgeProcessConfig {
  readonly runtimeRoot: string
  readonly python: string
  readonly env: Record<string, string>
  readonly policySource: string
  readonly expectedPolicyHash: string
  readonly enabledWorkloads: readonly string[]
  readonly auditPath: string
  readonly disposeGraceMs: number
  /** Maximum time in milliseconds to wait for one worker response. */
  readonly responseTimeoutMs: number
}
type Spawn = (spec: SubprocessSpawnSpec) => SubprocessHandle
export type GovernedRoute = { readonly taskKind: GovernedTaskKind, readonly reasonCode: GovernedReasonCode }
/** One strict JSONL connection with at most one pending response. */
export class GovernanceWorkerConnection {
  private readonly child: SubprocessHandle
  private readonly lines
  private pending: {
    resolve: (response: ReadyResponse | OperationalResponse) => void
    reject: (error: Error) => void
  } | undefined
  private terminalError: Error | undefined
  private disposed = false
  private terminationRequested = false
  constructor(spawn: Spawn, private readonly config: BridgeProcessConfig) {
    this.child = spawn({ argv: [config.python, '-m', 'dsh_runtime.governance_worker'], cwd: config.runtimeRoot, stdio: { stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' }, graceMs: config.disposeGraceMs, env: { PYTHONPATH: config.runtimeRoot, ...config.env } })
    if (this.child.stdin === undefined || this.child.stdout === undefined)
      throw new Error('governance worker requires piped stdin and stdout')
    this.lines = createInterface({ input: this.child.stdout, crlfDelay: Infinity })
    this.lines.on('line', (line) => { this.onLine(line) })
    this.lines.on('close', () => { this.fail(new Error('governance worker stdout ended unexpectedly')) })
    void this.child.done.then((outcome) => { this.fail(new Error(`governance worker exited (${String(outcome.exitCode)})`)) }, () => { this.fail(new Error('governance worker process failed')) })
  }
  /** Initialize the worker and return its fixed policy identity.
   * @param config - worker configuration and expected policy identity.
   * @returns the worker READY response.
   */
  async initialize(config: BridgeProcessConfig): Promise<ReadyResponse> {
    const request: InitializeRequest = { kind: 'INITIALIZE', protocol_version: GOVERNANCE_PROTOCOL_VERSION, policy_source: config.policySource, expected_policy_hash: config.expectedPolicyHash, enabled_workloads: config.enabledWorkloads, audit_path: config.auditPath }
    const response = await this.exchange(request)
    if (response.kind !== 'READY')
      throw new Error('governance worker did not become READY')
    return response
  }
  /** Send one operational request and validate its correlated response.
   * @param request - one bind-session or pre-start evaluation request.
   * @returns the correlated worker response.
   */
  async request(request: BindSessionRequest | EvaluatePreStartRequest): Promise<OperationalResponse> {
    const response = await this.exchange(request)
    if (response.kind === 'READY')
      throw new Error('unexpected READY response')
    if (response.request_id !== request.request_id) {
      const error = new Error('governance worker response correlation mismatch')
      this.fail(error)
      throw error
    }
    return response
  }
  private exchange(
    request: InitializeRequest | BindSessionRequest | EvaluatePreStartRequest,
  ): Promise<ReadyResponse | OperationalResponse> {
    if (this.disposed || this.terminalError !== undefined)
      return Promise.reject(this.terminalError ?? new Error('governance worker connection is disposed'))
    if (this.pending !== undefined)
      return Promise.reject(new Error('governance worker already has an in-flight request'))
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        const error = new Error(`governance worker response timed out after ${this.config.responseTimeoutMs}ms`)
        this.fail(error)
        this.terminateChild()
      }, this.config.responseTimeoutMs)
      this.pending = {
        resolve: (response) => { clearTimeout(timeout); resolve(response) },
        reject: (error) => { clearTimeout(timeout); reject(error) },
      }
      this.child.stdin?.write(encodeWorkerRequest(request), (error?: Error | null) => { if (error !== undefined && error !== null)
        this.fail(new Error('governance worker write failed')) })
    })
  }
  private onLine(line: string): void {
    const pending = this.pending
    if (pending === undefined) {
      this.fail(new Error('governance worker emitted an unsolicited response'))
      return
    }
    this.pending = undefined
    try {
      pending.resolve(parseWorkerResponse(line))
    }
    catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error))
      pending.reject(normalized)
      this.fail(normalized)
    }
  }
  private fail(error: Error): void { if (this.terminalError !== undefined || this.disposed)
    return; this.terminalError = error; const pending = this.pending; this.pending = undefined; pending?.reject(error) }
  /** Dispose the connection and wait for the managed worker range to exit. */
  async dispose(): Promise<void> {
    if (this.disposed)
      return
    this.disposed = true
    this.pending?.reject(new Error('governance worker connection disposed'))
    this.pending = undefined
    this.lines.removeAllListeners()
    this.lines.close()
    try {
      this.child.stdin?.end()
    }
    catch { }
    this.terminateChild()
    await this.child.waitForExit()
    await this.child.done.catch(() => undefined)
  }
  private terminateChild(): void {
    if (this.terminationRequested)
      return
    this.terminationRequested = true
    this.child.terminate()
  }
}
/** Closed Host-supported workload/reason pairs forwarded without inference. */
export const SUPPORTED_GOVERNED_START_PAIRS = Object.freeze([
  { taskKind: 'repository_change', reasonCode: 'host_v1_repository_change' },
  { taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection' },
] as const)
/** One exact workload/reason pair supported by the Host governance profiles. */
export type SupportedGovernedStartPair = typeof SUPPORTED_GOVERNED_START_PAIRS[number]
/** Test one Host route against the closed supported pair set.
 * @param route - the workload and reason registered by the Host.
 * @returns whether the route is one of the supported exact pairs.
 */
export function isSupportedGovernedStartPair(
  route: GovernedRoute,
): route is SupportedGovernedStartPair {
  return SUPPORTED_GOVERNED_START_PAIRS.some(candidate =>
    candidate.taskKind === route.taskKind && candidate.reasonCode === route.reasonCode)
}
/** Bridge-owned FIFO: one whole bind-plus-evaluate transaction at a time. */
export class GovernanceBridge {
  private readonly connection: GovernanceWorkerConnection
  private readonly ready: Promise<ReadyResponse>
  private tail: Promise<void> = Promise.resolve()
  private disposed = false
  constructor(spawn: Spawn, private readonly projections: Pick<SessionProjectionRegistry, 'stateOf'>, config: BridgeProcessConfig) {
    this.connection = new GovernanceWorkerConnection(spawn, config)
    this.ready = this.connection.initialize(config)
    void this.ready.catch(() => undefined)
  }
  /** Wait for the one-time worker initialization and exact policy identity pin.
   * @returns the READY response that confirms the worker's policy identity.
   */
  waitForReady(): Promise<ReadyResponse> { return this.ready }
  /** Govern one supported exact workload/reason ingress without invoking execution.
   * @param session - Session whose policy identity is pinned.
   * @param callerId - trusted parent Agent identity.
   * @param route - Host-registered workload and reason facts.
   * @returns the authoritative governance decision or a bridge failure.
   */
  evaluatePreStart(session: Session, callerId: string, route: GovernedRoute): Promise<GovernanceDecision | GovernanceFailure> {
    if (!isSupportedGovernedStartPair(route))
      return Promise.resolve({ ...bridgeFailure(null), diagnostic: 'governed route facts are not one of the supported exact pairs' })
    const governedRoute = route
    if (this.disposed)
      return Promise.resolve(bridgeFailure(null))
    const result = this.tail.then(async () => {
      if (this.disposed)
        return bridgeFailure(null)
      let evaluationId: string | null = null
      try {
        await this.ready
        let pin = governancePolicyPin(this.projections, session)
        const bindId = randomUUID()
        const bind: BindSessionRequest = pin === undefined ? { kind: 'BIND_SESSION', request_id: bindId, session_id: session.id, mode: 'create' } : { kind: 'BIND_SESSION', request_id: bindId, session_id: session.id, mode: 'resume', pinned_policy_identity: pin }
        const bound = await this.connection.request(bind)
        if (bound.kind === 'FAILURE')
          return bound
        if (bound.kind !== 'SESSION_BOUND' || bound.session_id !== session.id)
          return bridgeFailure(bindId)
        if (pin === undefined) {
          recordGovernancePolicyPin(this.projections, session, bound.policy_identity)
          pin = bound.policy_identity
        }
        evaluationId = randomUUID()
        const response = await this.connection.request({
          kind: 'EVALUATE_PRE_START',
          request_id: evaluationId,
          session_id: session.id,
          caller_id: callerId,
          pinned_policy_identity: pin,
          task_kind: governedRoute.taskKind,
          reason_code: governedRoute.reasonCode,
          request_structure: {
            request_type: 'subagent_one_shot_start',
            required_fields: ['parent', 'prompt', 'signal'],
          },
        })
        return response.kind === 'SESSION_BOUND' ? bridgeFailure(evaluationId) : response
      }
      catch {
        return bridgeFailure(evaluationId)
      }
    })
    this.tail = result.then(() => undefined, () => undefined)
    return result
  }
  /** Stop admission, settle queued work, and prove the worker range quiescent. */
  async dispose(): Promise<void> {
    if (this.disposed)
      return
    this.disposed = true
    try {
      await this.connection.dispose()
    }
    finally {
      await this.tail
    }
  }
}
