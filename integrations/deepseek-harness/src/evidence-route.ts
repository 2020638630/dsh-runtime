/** Authenticated Web read of one parent-owned external Runtime run. */

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-session-query'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { readTerminalEvidence, readTerminalRunState } from './runtime/read-terminal-evidence.ts'

/** Authenticated Host path for one parent Session's Runtime evidence. */
export const RUNTIME_EVIDENCE_PATH = '/api/dsh-runtime.evidence'
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u

/** Install under Connection's authentication fence when Web services are composed.
 * @param ctx - composed Host services with Session ownership data.
 * @param evidenceRoot - absolute Host-owned evidence directory.
 */
export function registerRuntimeEvidenceRoute(ctx: Context, evidenceRoot: string): () => Promise<void> {
  return ctx.connection.fetch.register({
    path: RUNTIME_EVIDENCE_PATH,
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async (request) => {
      const query = new URL(request.url).searchParams
      const parentId = query.get('sessionId')
      const childId = query.get('childId')
      if (parentId === null || parentId.length === 0 || childId === null || !UUID.test(childId)) {
        return new Response('Invalid Runtime evidence coordinates.', { status: 400 })
      }
      try {
        const parent = await ctx.sessionQuery.readSession(parentId as SessionId)
        const owned = parent.events.some(event => event.type === 'subagent/catalog'
          && event.data.version === 2
          && event.data.childId === childId)
        if (!owned) return new Response('Runtime evidence not found for this Session.', { status: 404 })
        const coordinates = {
          evidenceRoot, runId: `dsh-runtime-${childId}`, workspaceId: parentId,
        }
        const evidence = await readTerminalEvidence(coordinates)
        if (evidence === null) {
          const state = await readTerminalRunState(coordinates)
          if (state === null) return new Response('Runtime evidence not found.', { status: 404 })
          return Response.json({ state }, { status: state.phase === 'running' ? 202 : 200,
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
