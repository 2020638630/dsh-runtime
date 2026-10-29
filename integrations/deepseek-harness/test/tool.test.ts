import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { SubagentRuntime } from '@deepseek-ai/dsh-subagent'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'
import { createRuntimeTool } from '../src/tool.ts'

test('dedicated tool refuses calls without a trusted Host agent', async () => {
  let starts = 0
  const subagents = { startActivation: async () => { starts++; return { childId: 'child' } } } as unknown as Pick<SubagentRuntime, 'startActivation'>
  const tool = createRuntimeTool(subagents)
  await assert.rejects(tool.execute({ task_kind: 'repository_inspection', prompt: 'inspect', description: 'inspect' }, {
    signal: new AbortController().signal,
  } as ToolRunContext), /trusted calling agent/)
  assert.equal(starts, 0)
})

test('dedicated tool chooses the fixed inspection provider', async () => {
  let selected = ''
  const parent = { id: 'parent', session: { id: 'session' } }
  const subagents = { startActivation: async (spec: { provider: string, request: { parent: unknown }, delivery: string }) => {
    selected = spec.provider
    assert.equal(spec.request.parent, parent)
    assert.equal(spec.delivery, 'parent')
    return { childId: 'child' }
  } } as unknown as Pick<SubagentRuntime, 'startActivation'>
  const tool = createRuntimeTool(subagents)
  const result = await tool.execute({ task_kind: 'repository_inspection', prompt: 'inspect', description: 'inspect' }, {
    agent: parent, signal: new AbortController().signal,
  } as ToolRunContext)
  assert.equal(selected, 'dsh-runtime-inspection')
  assert.deepEqual(result, { subagentId: 'child' })
})

test('tool returns only a start receipt and directs the parent to await subagent status', async () => {
  const childId = '40af8fec-97fc-44bf-9036-8038906a7e11'
  const parent = { id: 'parent', session: { id: 'session' } }
  const subagents = { startActivation: async () => ({ childId }) } as unknown as Pick<SubagentRuntime, 'startActivation'>
  const tool = createRuntimeTool(subagents)
  assert.match(tool.description, /result arrives later as a subagent status update/)
  assert.match(tool.description, /not a background job ID/)
  const receipt = await tool.execute({ task_kind: 'repository_inspection', prompt: 'inspect', description: 'inspect' }, {
    agent: parent, signal: new AbortController().signal,
  } as ToolRunContext)
  assert.deepEqual(receipt, { subagentId: childId })
  const rendered = tool.output.render({}, receipt)
  assert.deepEqual(rendered, [{ type: 'text', text: `started governed DSH Runtime task ${childId}` }])
  assert.ok(!JSON.stringify(rendered).includes('completed'))
})
