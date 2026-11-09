import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-subprocess'

const CLI_LOGIN_PATH = '/api/dsh-runtime.cli-login'
const HELPER = fileURLToPath(new URL('../scripts/cli-login.py', import.meta.url))
const UI_HEADER = 'x-dsh-runtime-cli'
const statuses = new Set(['signed_in', 'signed_out', 'unavailable', 'unknown', 'unsupported'])

type Cli = 'codex' | 'codebuddy'
type Operation = 'status' | 'login'

interface Config {
  readonly python: string
  readonly runtimeRoot: string
  readonly env: Record<string, string>
  readonly disposeGraceMs: number
}

/** Host-owner access to fixed status checks and explicitly opened Windows login windows. */
export function registerCliLoginRoute(ctx: Context, config: Config): () => Promise<void> {
  if (process.platform !== 'win32' || process.env.ELECTRON_RUN_AS_NODE !== '1') return async () => {}
  const lifetime = new AbortController()
  const checking = new Map<Cli, Promise<string>>()
  const signingIn = new Set<Cli>()

  async function invoke(operation: Operation, cli: Cli, requestSignal?: AbortSignal): Promise<string> {
    try {
      const signal = AbortSignal.any([
        lifetime.signal, AbortSignal.timeout(operation === 'status' ? 18_000 : 550_000),
        ...(requestSignal ? [requestSignal] : []),
      ])
      signal.throwIfAborted()
      const child = ctx.subprocess.spawn({
        argv: [config.python, '-B', HELPER, operation, cli],
        cwd: config.runtimeRoot,
        stdio: { stdin: 'ignore', stdout: { maxBytes: 64 }, stderr: { maxBytes: 1 } },
        graceMs: config.disposeGraceMs,
        env: { PYTHONPATH: config.runtimeRoot, ...config.env },
        signal,
      })
      const result = await child.done
      if (signal.aborted) await child.waitForExit(AbortSignal.timeout(config.disposeGraceMs))
      const output = child.collected.stdout?.readFrom(0)
      const value = output?.text.trim() ?? ''
      if (result.exitCode === 0 && !signal.aborted && output?.lossy === false
        && (statuses.has(value) || (operation === 'login' && value === 'closed'))) return value
    } catch {
      // Never relay subprocess diagnostics or account data to the client or logs.
    }
    return 'unknown'
  }

  const disposeRoute = ctx.connection.fetch.register({
    path: CLI_LOGIN_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: async request => {
      const response = (status: string, code = 200) => Response.json({ status }, {
        status: code, headers: { 'cache-control': 'no-store' },
      })
      // Desktop's authenticated proxy removes the browser Origin and Fetch Metadata headers.
      if (request.headers.get(UI_HEADER) !== '1' || request.headers.has('origin')
        || request.headers.has('sec-fetch-site') || request.body !== null) return response('unknown', 403)
      const query = new URL(request.url).searchParams
      const cli = query.get('cli')
      const operation = query.get('operation')
      if ((cli !== 'codex' && cli !== 'codebuddy') || (operation !== 'status' && operation !== 'login')
        || [...query].length !== 2) return response('unknown', 400)
      if (signingIn.has(cli)) return response('running', operation === 'login' ? 409 : 200)
      if (operation === 'login') {
        signingIn.add(cli)
        try {
          await checking.get(cli)
          return response(await invoke(operation, cli, request.signal))
        } finally {
          signingIn.delete(cli)
        }
      }
      let check = checking.get(cli)
      if (!check) {
        check = invoke(operation, cli).finally(() => { checking.delete(cli) })
        checking.set(cli, check)
      }
      return response(await check)
    },
  })
  return async () => {
    lifetime.abort()
    await disposeRoute()
  }
}
