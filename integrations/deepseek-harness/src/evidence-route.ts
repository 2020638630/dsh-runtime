import { publicPreviews } from './runtime/public-preview.ts'
/** Authenticated Web read of one parent-owned external Runtime run. */

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-session-query'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { readTerminalEvidence, readTerminalRunState } from './runtime/read-terminal-evidence.ts'
import { readLiveProgress } from './runtime/read-live-progress.ts'
import { previewReviewMaterial } from './runtime/review-preview.ts'
import { activityHistories, resolveActivityEvidenceRoot } from './runtime/activity-history.ts'

/** Authenticated Host path for one parent Session's Runtime evidence. */
export const RUNTIME_EVIDENCE_PATH = '/api/dsh-runtime.evidence'
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u

/** Install under Connection's authentication fence when Web services are composed.
 * @param ctx - composed Host services with Session ownership data.
 * @param evidenceRoot - absolute Host-owned evidence directory.
 */
export function registerRuntimeEvidenceRoute(ctx: Context, evidenceRoot: string): () => Promise<void> {
  let previewInProgress = false
  return ctx.connection.fetch.register({
    path: RUNTIME_EVIDENCE_PATH,
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async (request) => {
      const query = new URL(request.url).searchParams
      const parentId = query.get('sessionId')
      const childId = query.get('childId')
      const preview = query.get('view') === 'review-preview'
      if (parentId === null || parentId.length === 0 || childId === null || !UUID.test(childId)) {
        return new Response('Invalid Runtime evidence coordinates.', { status: 400 })
      }
      if (preview && [...query].length !== 3) {
        return new Response('Invalid Runtime review preview coordinates.', { status: 400 })
      }
      try {
        const parent = await ctx.sessionQuery.readSession(parentId as SessionId)
        const owned = parent.events.some(event => event.type === 'subagent/catalog'
          && event.data.version === 2
          && event.data.childId === childId)
        if (!owned) return new Response('Runtime evidence not found for this Session.', { status: 404 })
        if (query.get('view') === 'public-preview') {
          if ([...query].length !== 3 || new Set(query.keys()).size !== 3
            || [...query.keys()].some(name => !['sessionId', 'childId', 'view'].includes(name))) {
            return new Response('Invalid public preview coordinates.', { status: 400 })
          }
          return Response.json(publicPreviews.read({ evidenceRoot: resolveActivityEvidenceRoot(evidenceRoot),
            runId: `dsh-runtime-${childId}`, workspaceId: parentId }),
          { headers: { 'cache-control': 'no-store' } })
        }
        if (query.get('view') === 'activity') {
          const after = query.get('after') ?? '0'
          const stream = query.get('stream') ?? undefined
          if (!/^(?:0|[1-9][0-9]{0,15})$/u.test(after) || !Number.isSafeInteger(Number(after))
            || (stream !== undefined && !UUID.test(stream))
            || [...query.keys()].some(name => !['sessionId', 'childId', 'view', 'after', 'stream'].includes(name))
            || new Set(query.keys()).size !== [...query.keys()].length) {
            return new Response('Invalid activity cursor.', { status: 400 })
          }
          return Response.json(activityHistories.read({ evidenceRoot: resolveActivityEvidenceRoot(evidenceRoot),
            runId: `dsh-runtime-${childId}`, workspaceId: parentId }, Number(after), stream),
          { headers: { 'cache-control': 'no-store' } })
        }
        const coordinates = {
          evidenceRoot, runId: `dsh-runtime-${childId}`, workspaceId: parentId,
        }
        const evidence = await readTerminalEvidence({ ...coordinates, includeReviewBytes: preview })
        if (preview) {
          const headers = { 'cache-control': 'no-store' }
          if (previewInProgress) return Response.json({ status: 'busy' }, { headers })
          previewInProgress = true
          try {
            const material = evidence === null ? { status: 'unsupported_run' }
              : await previewReviewMaterial(evidence, parent.session.cwd, request.signal)
            return Response.json(material, { headers })
          } finally {
            previewInProgress = false
          }
        }
        if (evidence === null) {
          const state = await readTerminalRunState(coordinates)
          if (state === null) return new Response('Runtime evidence not found.', { status: 404 })
          const progress = state.phase === 'running' ? await readLiveProgress(coordinates) : undefined
          return Response.json({ state, progress }, { status: state.phase === 'running' ? 202 : 200,
            headers: { 'cache-control': 'no-store' } })
        }
        return Response.json(evidence, { headers: { 'cache-control': 'no-store' } })
      } catch (error: unknown) {
        request.signal.throwIfAborted()
        ctx.logger.warn(`subagent-dsh-runtime evidence read failed: ${error instanceof Error ? error.message : String(error)}`)
        return new Response('Runtime evidence unavailable.', { status: 500 })
      }
    },
  })
}
