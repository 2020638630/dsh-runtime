/** Explicit model tool selecting one of two fixed governed Runtime providers. */
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { SubagentRuntime } from '@deepseek-ai/dsh-subagent'
import { RUNTIME_PROVIDER_NAMES } from './provider.ts'

export function createRuntimeTool(subagents: Pick<SubagentRuntime, 'startActivation'>) {
  return defineTool({
    name: 'dsh_runtime',
    description: 'Run a governed DSH Runtime repository inspection or change in the current workspace.',
    parameters: {
      task_kind: { type: 'string', enum: ['repository_inspection', 'repository_change'], required: true },
      prompt: { type: 'string', required: true },
      description: { type: 'string', required: true },
    },
    output: {
      schema: {
        type: 'object', additionalProperties: false,
        properties: { subagentId: { type: 'string', required: true } },
      },
      render: (_args, value) => [{ type: 'text', text: `started governed DSH Runtime task ${value.subagentId}` }],
    },
    async execute(args, exec) {
      const parent = exec.agent
      if (parent === undefined) throw new Error('dsh_runtime requires a trusted calling agent')
      exec.signal.throwIfAborted()
      const started = await subagents.startActivation({
        provider: RUNTIME_PROVIDER_NAMES[args.task_kind],
        label: args.description,
        request: { parent, prompt: [{ type: 'text', text: args.prompt }] },
        signal: exec.signal,
        delivery: 'parent',
      })
      return { subagentId: started.childId }
    },
    presentCall: args => ({ card: 'generic', title: `DSH Runtime · ${args.task_kind}`, kind: args.task_kind === 'repository_change' ? 'edit' : 'read' }),
  })
}
