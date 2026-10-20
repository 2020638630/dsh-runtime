import { defineTool } from '@deepseek-ai/dsh-tools'
import { NO_START_CAPABILITIES } from '@deepseek-ai/dsh-subagent'

export const inject = ['tools', 'connection', 'subagents']

const PROVIDERS = Object.freeze({
  repository_inspection: 'dsh-runtime-inspection-probe',
  repository_change: 'dsh-runtime-change-probe',
})

export function apply(ctx) {
  for (const name of Object.values(PROVIDERS)) {
    ctx.subagents.registerProvider({
      name,
      capabilities: NO_START_CAPABILITIES,
      inheritsParentContext: false,
      start: () => { throw new Error('dsh runtime probe: governance is not installed') },
    })
  }
  const tool = defineTool({
    name: 'dsh_runtime_admission_probe',
    description: 'Test the external Runtime tool admission contract without starting a task.',
    parameters: {
      task_kind: {
        type: 'string',
        enum: ['repository_inspection', 'repository_change'],
        required: true,
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          selectedProvider: { type: 'string', required: true },
          started: { type: 'boolean', required: true },
        },
      },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    execute: async (args, exec) => {
      exec.signal.throwIfAborted()
      if (!exec.agent) throw new Error('dsh runtime probe: trusted calling agent required')
      return { selectedProvider: PROVIDERS[args.task_kind], started: false }
    },
  })
  ctx.tools.register(tool)
  ctx.connection.fetch.register({
    path: '/api/dsh-runtime-tool-probe',
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async () => {
      const schema = ctx.tools.get(tool.name)?.parameters
      const result = await ctx.tools.execute({
        name: tool.name,
        callId: 'admission-probe-no-agent',
        arguments: { task_kind: 'repository_inspection' },
        signal: new AbortController().signal,
      })
      const invalid = await ctx.tools.execute({
        name: tool.name,
        callId: 'admission-probe-invalid-kind',
        arguments: { task_kind: 'other' },
        signal: new AbortController().signal,
      })
      const cancellation = new AbortController()
      cancellation.abort()
      const aborted = await ctx.tools.execute({
        name: tool.name,
        callId: 'admission-probe-aborted',
        arguments: { task_kind: 'repository_inspection' },
        signal: cancellation.signal,
      })
      return Response.json({
        registered: schema !== undefined,
        hasTaskKind: schema?.properties?.task_kind !== undefined,
        inspectionProviderRegistered: ctx.subagents.getProvider(PROVIDERS.repository_inspection)?.name === PROVIDERS.repository_inspection,
        changeProviderRegistered: ctx.subagents.getProvider(PROVIDERS.repository_change)?.name === PROVIDERS.repository_change,
        noAgentRejected: result.isError === true && JSON.stringify(result).includes('trusted calling agent required'),
        invalidTaskKindRejected: invalid.isError === true,
        preAbortedRejected: aborted.isError === true,
      })
    },
  })
}
