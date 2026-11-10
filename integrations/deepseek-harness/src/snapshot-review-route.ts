import { createHash, randomUUID } from 'node:crypto'
import { lstat, mkdir, open, realpath, rename, writeFile } from 'node:fs/promises'
import { join, relative, isAbsolute, sep } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import { NO_START_CAPABILITIES } from '@deepseek-ai/dsh-subagent'
import type { ResolvedSubagentStartRequest, SubagentResult, SubagentRun } from '@deepseek-ai/dsh-subagent'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { z } from 'zod'
import { startGoverned } from './admission.ts'
import type { GovernanceBridge } from './governance/bridge.ts'
import { RUNTIME_ROUTES } from './provider.ts'
import { readTerminalEvidence } from './runtime/read-terminal-evidence.ts'
import { previewReviewMaterial } from './runtime/review-preview.ts'
import type { RuntimeLauncherConfig } from './runtime-launcher.ts'
import type { ApiRoleSelectionConfig } from './index.ts'

const PATH = '/api/dsh-runtime.snapshot-review'
const PROVIDER = 'dsh-runtime-snapshot-review'
const ID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const digest = z.string().regex(/^[0-9a-f]{64}$/u)
const model = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/u)
const confirm = z.strictObject({
  sessionId: z.string().min(1).max(128), childId: z.string().regex(ID),
  patchSha256: digest, worktreeSha256: digest, approvalToken: z.string().regex(ID),
})
const reviewReply = z.strictObject({
  patch_sha256: digest, observed_model: model.nullable(),
  verdict: z.enum(['PASS', 'FAIL', 'INCONCLUSIVE']), report: z.string().max(8192),
})
const claimSchema = z.strictObject({
  version: z.literal(1), reviewId: z.string().regex(ID),
  sourceRunId: z.string(), sourceTaskId: z.string().regex(ID),
  sessionId: z.string(), provider: z.enum(['openrouter', 'siliconflow']),
  requestedModel: model, workerModel: model, patchSha256: digest, worktreeSha256: digest,
  context: z.literal('fresh_tool_free_request'), material: z.literal('saved_text_patch'),
})
const savedResult = z.strictObject({
  reviewId: z.string().regex(ID), status: z.enum(['completed', 'identity_unverified', 'failed', 'timed_out', 'cancelled']),
  reportedModel: model.nullable().optional(), verdict: reviewReply.shape.verdict.optional(), report: z.string().max(8192).optional(),
})
type Claim = z.infer<typeof claimSchema>
type ReviewResult = z.infer<typeof savedResult>
type Parent = ResolvedSubagentStartRequest['parent']
type ReviewerConfig = Pick<RuntimeLauncherConfig, 'python' | 'runtimeRoot' | 'env' | 'disposeGraceMs'>
  & { evidenceRoot: string; reviewer: ApiRoleSelectionConfig }

// Keep inference conservative. A custom namespace, alias, or unknown model
// never supplies proof of diversity merely because it used another transport.
export function reviewModelFamily(value: string): string | undefined {
  const id = value.toLowerCase()
  const rules = [
    /^(?:openai\/)?(?:gpt-[0-9]|o[134](?:-|$))/u,
    /^(?:anthropic\/)?claude-/u,
    /^(?:google\/)?gemini-/u,
    /^(?:(?:deepseek|deepseek-ai)\/)?deepseek-/u,
    /^(?:(?:z-ai|zhipuai)\/)?glm-[0-9]/u,
    /^(?:(?:qwen|alibaba)\/)?qwen[0-9.-]/u,
  ]
  const index = rules.findIndex(rule => rule.test(id))
  return ['openai', 'anthropic', 'google', 'deepseek', 'zhipu', 'qwen'][index]
}

function workerIdentity(manifest: Record<string, unknown>): string | undefined {
  const observations = z.object({
    version: z.union([z.literal(1), z.literal(2)]), source: z.string().optional(),
    entries: z.array(z.object({
      role: z.string(), invocation_index: z.number(), adapter: z.string(),
      source: z.string().optional(), reported_model: model.nullable(),
    })).max(2),
  }).safeParse(manifest.model_observations)
  if (!observations.success) return
  const candidates = observations.data.entries.filter(row => row.role === 'worker')
  const row = candidates[0]
  if (candidates.length !== 1 || row.invocation_index !== 1 || row.reported_model === null) return
  const source = observations.data.version === 1 ? observations.data.source : row.source
  if ((row.adapter === 'codex' && source === 'codex_thread_start')
    || (row.adapter === 'codebuddy' && source === 'codebuddy_json_assistant')) return row.reported_model
}

async function plainDirectory(path: string, create = false): Promise<boolean> {
  if (create) await mkdir(path).catch((error: NodeJS.ErrnoException) => {
    if (error.code !== 'EEXIST') throw error
  })
  const info = await lstat(path).catch((error: NodeJS.ErrnoException) => {
    if (error.code !== 'ENOENT') throw error
  })
  if (!info) return false
  if (!info.isDirectory() || info.isSymbolicLink() || await realpath(path) !== path) {
    throw new Error('unsafe review ledger directory')
  }
  return true
}

async function readLedgerBytes(path: string): Promise<Buffer | undefined> {
  const info = await lstat(path).catch((error: NodeJS.ErrnoException) => {
    if (error.code !== 'ENOENT') throw error
  })
  if (!info) return
  if (!info.isFile() || info.nlink !== 1 || info.size > 65536) throw new Error('unsafe review ledger file')
  const file = await open(path, 'r')
  try {
    const opened = await file.stat()
    if (!opened.isFile() || opened.nlink !== 1 || opened.dev !== info.dev || opened.ino !== info.ino) {
      throw new Error('review ledger changed during read')
    }
    const bytes = Buffer.alloc(65537)
    const { bytesRead } = await file.read(bytes, 0, bytes.length, 0)
    if (bytesRead !== info.size) throw new Error('review ledger size changed')
    return bytes.subarray(0, bytesRead)
  } finally {
    await file.close()
  }
}

async function readLedger(path: string): Promise<unknown> {
  const bytes = await readLedgerBytes(path)
  return bytes && JSON.parse(bytes.toString('utf8'))
}

interface ReviewGrant {
  readonly parent: Parent
  readonly patch: string
  readonly claim: Claim
  readonly signal: AbortSignal
  reply?: z.infer<typeof reviewReply>
  timedOut?: boolean
}

export async function mountSnapshotReview(ctx: Context, config: ReviewerConfig, bridge: GovernanceBridge): Promise<() => Promise<void>> {
  const lifetime = new AbortController()
  const grants = new Map<string, ReviewGrant>()
  const previews = new Map<string, { sessionId: string; childId: string; patchSha256: string;
    worktreeSha256: string; expires: number }>()
  const running = new Map<string, Promise<void>>()
  let preparing = false
  const response = (value: unknown, status = 200) => Response.json(value, {
    status, headers: { 'cache-control': 'no-store' },
  })

  async function start(grant: ReviewGrant, request: ResolvedSubagentStartRequest): Promise<SubagentRun> {
    const signal = AbortSignal.any([request.signal, grant.signal])
    return startGoverned(bridge, request.parent.session, String(request.parent.id), RUNTIME_ROUTES.repository_inspection,
      signal, () => {
        const child = ctx.subprocess.spawn({
          argv: [config.python, '-B', '-m', 'dsh_runtime.snapshot_review'],
          cwd: config.runtimeRoot, env: { PYTHONPATH: config.runtimeRoot, ...config.env },
          stdio: { stdin: { data: JSON.stringify(grant.patch) }, stdout: { maxBytes: 65536 }, stderr: { maxBytes: 1 } },
          graceMs: config.disposeGraceMs, signal,
        })
        const result: Promise<SubagentResult> = child.done.then(done => {
          const output = child.collected.stdout?.readFrom(0)
          if (done.exitCode === 3) grant.timedOut = true
          if (signal.aborted || done.exitCode !== 0 || output?.lossy !== false) {
            return { stopReason: signal.aborted ? 'aborted' : 'error', output: [] }
          }
          try {
            const parsed = reviewReply.parse(JSON.parse(output.text))
            if (parsed.patch_sha256 === grant.claim.patchSha256) {
              grant.reply = parsed
              return { stopReason: 'completed', output: [] }
            }
          } catch { /* The transport and its diagnostics are private. */ }
          return { stopReason: 'error', output: [] }
        })
        return {
          id: randomUUID() as SessionId, result,
          async dispose() {
            child.terminate()
            await child.waitForExit(AbortSignal.timeout(config.disposeGraceMs))
          },
        }
      })
  }

  const unregisterProvider = ctx.subagents.registerProvider({
    name: PROVIDER, capabilities: NO_START_CAPABILITIES, inheritsParentContext: false,
    async start(request) {
      const block = request.prompt[0]
      const token = request.prompt.length === 1 && block?.type === 'text' ? block.text : ''
      const grant = grants.get(token)
      if (!grant || grant.parent !== request.parent) throw new Error('snapshot review requires a Host grant')
      grants.delete(token)
      return start(grant, request)
    },
  })

  async function dispatch(ledger: string, parent: Parent, patch: string, claim: Claim): Promise<void> {
    const deadline = AbortSignal.timeout(50_000)
    const signal = AbortSignal.any([lifetime.signal, deadline])
    const grant: ReviewGrant = { parent, patch, claim, signal }
    const token = randomUUID()
    grants.set(token, grant)
    let result: ReviewResult = { reviewId: claim.reviewId, status: 'failed' }
    try {
      const activation = await ctx.subagents.startActivation({
        provider: PROVIDER, label: 'DSH Runtime 追加只读复核',
        request: { parent, prompt: [{ type: 'text', text: token }] }, signal, delivery: 'caller',
      })
      const interrupt = () => { void activation.dispose().catch(() => undefined) }
      signal.addEventListener('abort', interrupt, { once: true })
      try {
        if (signal.aborted) interrupt()
        const outcome = await activation.result
        const reply = grant.reply
        if (outcome.stopReason === 'completed' && reply && !signal.aborted) {
          const reportedModel = reply.observed_model
          const family = reportedModel === null ? undefined : reviewModelFamily(reportedModel)
          const requestedName = claim.requestedModel.toLowerCase().split('/').at(-1)
          const verified = family !== undefined && family === reviewModelFamily(claim.requestedModel)
            && family !== reviewModelFamily(claim.workerModel)
            && reportedModel?.toLowerCase().split('/').at(-1) === requestedName
          result = verified
            ? { reviewId: claim.reviewId, status: 'completed', reportedModel, verdict: reply.verdict, report: reply.report }
            : { reviewId: claim.reviewId, status: 'identity_unverified', reportedModel }
        } else if (grant.timedOut) {
          result = { reviewId: claim.reviewId, status: 'timed_out' }
        }
      } finally {
        signal.removeEventListener('abort', interrupt)
      }
    } catch { /* An accepted claim is never dispatched again. */ }
    finally {
      grants.delete(token)
      if (signal.aborted) result = { reviewId: claim.reviewId, status: deadline.aborted ? 'timed_out' : 'cancelled' }
      const pending = join(ledger, 'result.pending')
      await writeFile(pending, JSON.stringify(result), { flag: 'wx' })
      await rename(pending, join(ledger, 'result.json'))
    }
  }

  let unregisterRoute: () => Promise<void>
  try { unregisterRoute = ctx.connection.fetch.register({
    path: PATH, methods: ['GET', 'POST'], requestBody: 'buffered',
    fetch: async request => {
      let input: z.infer<typeof confirm> | undefined
      const url = new URL(request.url)
      if (request.method === 'POST') {
        if (request.headers.get('x-dsh-runtime-review') !== '1' || request.headers.has('origin')
          || request.headers.has('sec-fetch-site')) return response({ status: 'denied' }, 403)
        if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json'
          || Number(request.headers.get('content-length')) > 2048) return response({ status: 'invalid' }, 400)
        try {
          const bytes = await request.arrayBuffer()
          if (bytes.byteLength > 2048 || url.search) return response({ status: 'invalid' }, 400)
          input = confirm.parse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)))
        } catch { return response({ status: 'invalid' }, 400) }
      }
      const sessionId = input?.sessionId ?? url.searchParams.get('sessionId')
      const childId = input?.childId ?? url.searchParams.get('childId')
      if (!sessionId || sessionId.length > 128 || !childId || !ID.test(childId)
        || (!input && [...url.searchParams].length !== 2)) return response({ status: 'invalid' }, 400)
      try {
        const parentLog = await ctx.sessionQuery.readSession(sessionId as SessionId)
        if (!parentLog.events.some(event => event.type === 'subagent/catalog'
          && event.data.version === 2 && event.data.childId === childId)) {
          return response({ status: 'denied' }, 404)
        }
        const sourceRunId = `dsh-runtime-${childId}`
        const root = await realpath(config.evidenceRoot)
        const directory = join(root, 'snapshot-reviews')
        const ledger = join(directory, sourceRunId)
        if (await plainDirectory(directory) && await plainDirectory(ledger)) {
          const claim = claimSchema.safeParse(await readLedger(join(ledger, 'claim.json')))
          if (!claim.success || claim.data.sessionId !== sessionId || claim.data.sourceRunId !== sourceRunId) {
            return response({ status: 'unknown' })
          }
          const saved = savedResult.safeParse(await readLedger(join(ledger, 'result.json')))
          const result = saved.success && saved.data.reviewId === claim.data.reviewId ? saved.data : null
          if (result === null) return response({ status: running.has(ledger) ? 'running' : 'unknown' })
          const patch = await readLedgerBytes(join(ledger, 'material.patch'))
          if (!patch || createHash('sha256').update(patch).digest('hex') !== claim.data.patchSha256) {
            return response({ status: 'unknown' })
          }
          let freshness = 'unknown'
          if (!preparing) {
            preparing = true
            try {
              const evidence = await readTerminalEvidence({
                evidenceRoot: root, runId: sourceRunId, workspaceId: sessionId, includeReviewBytes: true,
              })
              const preview = evidence && await previewReviewMaterial(evidence, parentLog.session.cwd, request.signal)
              if (preview?.status === 'ready' && preview.patchSha256 === claim.data.patchSha256
                && preview.worktreeSha256 === claim.data.worktreeSha256) freshness = 'matched'
              else if (preview?.status !== 'workspace_unavailable') freshness = 'stale'
            } finally {
              preparing = false
            }
          }
          return response({ ...result, freshness, claim: claim.data, patch: patch.toString('utf8') })
        }
        if (preparing || running.size > 0) return response({ status: 'busy' }, 409)
        preparing = true
        try {
          const evidence = await readTerminalEvidence({
            evidenceRoot: root, runId: sourceRunId, workspaceId: sessionId, includeReviewBytes: true,
          })
          if (!evidence) return response({ status: 'unsupported_run' })
          const preview = await previewReviewMaterial(evidence, parentLog.session.cwd, request.signal)
          if (preview.status !== 'ready') return response(preview)
          const sourceTaskId = evidence.manifest.task_id
          if (typeof sourceTaskId !== 'string' || !ID.test(sourceTaskId)) return response({ status: 'missing_binding' })
          const workerModel = workerIdentity(evidence.manifest)
          const family = workerModel && reviewModelFamily(workerModel)
          const reviewerFamily = reviewModelFamily(config.reviewer.model)
          if (!workerModel || !family || !reviewerFamily || family === reviewerFamily) {
            return response({ status: 'identity_unverified' })
          }
          const agents = ctx.get('agents') as { get(id: SessionId): Parent | undefined } | undefined
          const parent = agents?.get(sessionId as SessionId)
          const liveCwd = parent?.session.header.cwd
          if (!parent || !liveCwd || liveCwd !== parentLog.session.cwd) return response({ status: 'parent_unavailable' })
          const workspace = await realpath(liveCwd)
          const within = (base: string, path: string) => {
            const rel = relative(base, path)
            return !isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..${sep}`)
          }
          if (within(workspace, root) || within(root, workspace)) return response({ status: 'denied' }, 403)
          if (!input) {
            const now = Date.now()
            for (const [key, value] of previews) if (value.expires <= now) previews.delete(key)
            if (previews.size >= 32) return response({ status: 'busy' }, 409)
            const approvalToken = randomUUID()
            previews.set(approvalToken, {
              sessionId, childId, patchSha256: preview.patchSha256, worktreeSha256: preview.worktreeSha256,
              expires: now + 120_000,
            })
            return response({
              status: 'ready', approvalToken, provider: config.reviewer.provider, requestedModel: config.reviewer.model,
              workerModel, patchSha256: preview.patchSha256, worktreeSha256: preview.worktreeSha256,
            })
          }
          const approval = previews.get(input.approvalToken)
          if (!approval || approval.expires <= Date.now() || approval.sessionId !== sessionId || approval.childId !== childId
            || approval.patchSha256 !== input.patchSha256 || approval.worktreeSha256 !== input.worktreeSha256
            || input.patchSha256 !== preview.patchSha256 || input.worktreeSha256 !== preview.worktreeSha256) {
            return response({ status: 'stale' }, 409)
          }
          previews.delete(input.approvalToken)
          request.signal.throwIfAborted()
          await plainDirectory(directory, true)
          try { await mkdir(ledger) } catch (error) {
            if ((error as NodeJS.ErrnoException).code === 'EEXIST') return response({ status: 'busy' }, 409)
            throw error
          }
          const claim: Claim = {
            version: 1, reviewId: randomUUID(), sourceRunId, sourceTaskId, sessionId,
            provider: config.reviewer.provider, requestedModel: config.reviewer.model, workerModel,
            patchSha256: preview.patchSha256, worktreeSha256: preview.worktreeSha256,
            context: 'fresh_tool_free_request', material: 'saved_text_patch',
          }
          await writeFile(join(ledger, 'material.patch'), preview.patch, { flag: 'wx' })
          const file = await open(join(ledger, 'claim.json'), 'wx')
          try {
            await file.writeFile(JSON.stringify(claim))
            await file.sync()
          } finally {
            await file.close()
          }
          running.set(ledger, dispatch(ledger, parent, preview.patch, claim)
            .catch(() => undefined).finally(() => { running.delete(ledger) }))
          return response({ status: 'running' }, 202)
        } finally {
          preparing = false
        }
      } catch {
        return response({ status: 'unavailable' }, 503)
      }
    },
  }) } catch (error) {
    await unregisterProvider()
    throw error
  }
  return async () => {
    lifetime.abort()
    await unregisterRoute()
    await Promise.all(running.values())
    await unregisterProvider()
  }
}
