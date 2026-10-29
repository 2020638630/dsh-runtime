import { writeFile } from 'node:fs/promises'
export const inject = ['tools']
export function apply(ctx, config) {
  let stopped = false
  ctx.effect(() => () => { stopped = true })
  void (async () => {
    try {
      const name = 'mcp__fixture__ping'
      const deadline = Date.now() + 12000
      while (!stopped && !ctx.tools.get(name) && Date.now() < deadline) await new Promise(r => setTimeout(r, 100))
      const schemas = ctx.tools.schemas().map(x => x.name)
      const result = await ctx.tools.execute({ name, arguments: { payload: 'synthetic-body-marker' }, callId: 'mcp-probe', signal: AbortSignal.timeout(5000) })
      await writeFile(config.output, JSON.stringify({schemas, result}))
    } catch (error) { await writeFile(config.output, JSON.stringify({error: String(error), stack: error.stack})) }
  })()
}
