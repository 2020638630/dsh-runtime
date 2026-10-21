/** Acceptance-only probe: inspect the external plugin through official Host services. */
export const inject = ['connection', 'tools', 'subagents', 'workspaceRegistry', 'sessionQuery']

export function apply(ctx, config = {}) {
  ctx.connection.fetch.register({
    path: '/api/dsh-runtime-status-probe',
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async () => {
      const schema = ctx.tools.get('dsh_runtime')?.parameters
      const base = {
        task_kind: 'repository_inspection',
        prompt: 'No-model admission probe only',
        description: 'No-model admission probe only',
      }
      const noAgent = await ctx.tools.execute({
        name: 'dsh_runtime', callId: 'runtime-status-no-agent',
        arguments: base, signal: new AbortController().signal,
      })
      const invalidKind = await ctx.tools.execute({
        name: 'dsh_runtime', callId: 'runtime-status-invalid-kind',
        arguments: { ...base, task_kind: 'other' }, signal: new AbortController().signal,
      })
      const cancellation = new AbortController()
      cancellation.abort()
      const preAborted = await ctx.tools.execute({
        name: 'dsh_runtime', callId: 'runtime-status-pre-aborted',
        arguments: base, signal: cancellation.signal,
      })
      return Response.json({
        toolRegistered: schema !== undefined,
        taskKindEnum: schema?.properties?.task_kind?.enum,
        inspectionProvider: ctx.subagents.getProvider('dsh-runtime-inspection')?.name === 'dsh-runtime-inspection',
        changeProvider: ctx.subagents.getProvider('dsh-runtime-change')?.name === 'dsh-runtime-change',
        noAgentRejected: noAgent.isError === true && JSON.stringify(noAgent).includes('trusted calling agent'),
        invalidKindRejected: invalidKind.isError === true,
        preAbortedRejected: preAborted.isError === true,
      })
    },
  })
  ctx.connection.fetch.register({
    path: '/api/dsh-runtime-status-probe/workspace',
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: async () => {
      if (typeof config.trialRoot !== 'string' || config.trialRoot.length === 0)
        return Response.json({ error: 'trialRoot is not configured' }, { status: 503 })
      const workspace = await ctx.workspaceRegistry.create(config.trialRoot, config.trialTitle ?? 'runtime-readonly-trial')
      return Response.json({ workspaceId: workspace.id, path: workspace.path })
    },
  })
  ctx.connection.fetch.register({
    path: '/api/dsh-runtime-status-probe/session',
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async () => {
      if (!config.parentId) return Response.json({ error: 'parentId is not configured' }, { status: 503 })
      try {
        const session = await ctx.sessionQuery.readSession(config.parentId)
        return Response.json({
          eventCount: session.events.length,
          catalog: session.events.filter(event => event.type === 'subagent/catalog').map(event => ({ version: event.data.version, childId: event.data.childId })),
        })
      } catch (error) {
        return Response.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 })
      }
    },
  })
  if (config.allowInterrupt === true) ctx.connection.fetch.register({
    path: '/api/dsh-runtime-status-probe/interrupt',
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: async request => {
      const body = await request.json().catch(() => null)
      const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/
      if (!/^session-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(body?.parentId ?? '')
        || !uuid.test(body?.childId ?? ''))
        return Response.json({ error: 'invalid parent or child id' }, { status: 400 })
      ctx.subagents.interrupt(body.childId, { kind: 'user', parentSessionId: body.parentId })
      return Response.json({ accepted: true })
    },
  })
}
