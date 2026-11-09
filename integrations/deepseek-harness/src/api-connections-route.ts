import { randomBytes } from 'node:crypto'
import { realpathSync } from 'node:fs'
import { dirname, isAbsolute, relative, sep } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-subprocess'
import { z } from 'zod'

const PATH = '/api/dsh-runtime.api-connections'
const REQUEST_LIMIT = 2048
const provider = z.enum(['openrouter', 'siliconflow'])
const reference = z.string().regex(/^[A-Za-z][A-Za-z0-9_-]{0,63}$/u)
const revision = z.string().regex(/^[0-9a-f]{64}$/u)
const requestBody = z.union([
  z.strictObject({ action: z.literal('list') }),
  z.strictObject({
    action: z.enum(['save', 'test']), reference, provider, revision,
    key: z.string().regex(/^[\x21-\x7e]{8,512}$/u).nullable(),
  }),
])
const catalogReply = z.strictObject({
  status: z.literal('ok'), revision,
  connections: z.array(z.strictObject({ reference, provider, keySet: z.literal(true) })),
})
const failures = z.enum(['invalid', 'conflict', 'unavailable'])
const trialReply = z.enum([
  'authenticated', 'model_catalog_readable', 'auth_rejected', 'rate_limited',
  'redirect_rejected', 'http_error', 'invalid_response', 'timeout', 'network_error', 'client_unavailable',
])
const statusReply = z.strictObject({ status: z.union([failures, trialReply]) })

interface Config {
  readonly python: string
  readonly runtimeRoot: string
  readonly env: Record<string, string>
  readonly disposeGraceMs: number
  readonly auditPath: string
  readonly evidenceRoot: string
  readonly apiAgentConnectionsPath?: string
}

function inEvidence(path: string, root: string): boolean {
  const distance = relative(realpathSync(root), realpathSync(dirname(path)))
  return distance === '' || (distance !== '..' && !distance.startsWith('..' + sep) && !isAbsolute(distance))
}

/** The authenticated desktop owner can administer only its configured catalog. */
export function registerApiConnectionsRoute(ctx: Context, config: Config): () => Promise<void> {
  if (process.platform !== 'win32' || process.env.ELECTRON_RUN_AS_NODE !== '1') return async () => {}
  const lifetime = new AbortController()
  const catalog = config.apiAgentConnectionsPath ?? config.auditPath + '.api-connections.json'
  const secret = randomBytes(32).toString('hex')
  const response = (body: unknown, status = 200) => Response.json(body, {
    status, headers: { 'cache-control': 'no-store' },
  })
  const disposeRoute = ctx.connection.fetch.register({
    path: PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: async request => {
      // The Desktop proxy strips these headers. Browser-origin writes are not accepted.
      if (request.headers.get('x-dsh-runtime-api') !== '1' || request.headers.has('origin')
        || request.headers.has('sec-fetch-site')) return response({ status: 'unavailable' }, 403)
      const jsonType = request.headers.get('content-type')?.split(';')[0].trim().toLowerCase()
      if (new URL(request.url).search || jsonType !== 'application/json'
        || Number(request.headers.get('content-length')) > REQUEST_LIMIT) {
        return response({ status: 'invalid' }, 400)
      }
      let action: z.infer<typeof requestBody>
      try {
        const bytes = await request.arrayBuffer()
        if (bytes.byteLength > REQUEST_LIMIT) return response({ status: 'invalid' }, 400)
        action = requestBody.parse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)))
      } catch {
        return response({ status: 'invalid' }, 400)
      }
      try {
        if (inEvidence(catalog, config.evidenceRoot)) return response({ status: 'unavailable' }, 503)
        const signal = AbortSignal.any([
          lifetime.signal, AbortSignal.timeout(12_000),
          ...(action.action === 'save' ? [] : [request.signal]),
        ])
        signal.throwIfAborted()
        // The key travels only in bounded stdin. Neither argv, environment nor diagnostics contain it.
        const child = ctx.subprocess.spawn({
          argv: [config.python, '-B', '-m', 'dsh_runtime.api_agent_connection_admin', catalog],
          cwd: config.runtimeRoot,
          stdio: { stdin: { data: JSON.stringify({ request: action, secret }) },
            stdout: { maxBytes: 65_536 }, stderr: { maxBytes: 1 } },
          env: { PYTHONPATH: config.runtimeRoot, ...config.env },
          graceMs: config.disposeGraceMs,
          signal,
        })
        const result = await child.done
        const output = child.collected.stdout?.readFrom(0)
        if (result.exitCode === 0 && !signal.aborted && output?.lossy === false) {
          const value: unknown = JSON.parse(output.text)
          if (action.action !== 'test') {
            const parsed = catalogReply.safeParse(value)
            if (parsed.success) return response(parsed.data)
          }
          const status = statusReply.safeParse(value)
          if (status.success) {
            const tag = status.data.status
            if (tag === 'conflict') return response(status.data, 409)
            if (tag === 'invalid') return response(status.data, 400)
            if (tag === 'unavailable') return response(status.data, 503)
            if (action.action === 'test') return response(status.data)
          }
        }
      } catch {
        // Do not echo exception, provider response, request body or filesystem paths.
      }
      return response({ status: 'unavailable' }, 503)
    },
  })
  return async () => {
    lifetime.abort()
    await disposeRoute()
  }
}
