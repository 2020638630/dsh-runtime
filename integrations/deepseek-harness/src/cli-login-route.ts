import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-subprocess'
import { z } from 'zod'
import { MODEL_OUTPUT_BYTES, modelCatalogReply } from './model-catalog.ts'

const CLI_LOGIN_PATH = '/api/dsh-runtime.cli-login'
const HELPER = fileURLToPath(new URL('../scripts/cli-login.py', import.meta.url))
const UI_HEADER = 'x-dsh-runtime-cli'
const statuses = new Set(['signed_in', 'signed_out', 'unavailable', 'unknown', 'unsupported'])
const modelFailure = z.strictObject({ status: z.enum([
  'signed_out', 'unavailable', 'unknown', 'unsupported', 'invalid_response', 'timeout',
]) })
const modelReply = z.union([modelCatalogReply, modelFailure])

type Cli = 'codex' | 'codebuddy'
type Operation = 'status' | 'login' | 'models'

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
  let catalog: Promise<z.infer<typeof modelReply>> | undefined

  async function runHelper(operation: Operation, cli: Cli, requestSignal?: AbortSignal): Promise<string | undefined> {
    try {
      const signal = AbortSignal.any([
        lifetime.signal, AbortSignal.timeout(operation === 'login' ? 550_000 : 18_000),
        ...(requestSignal ? [requestSignal] : []),
      ])
      signal.throwIfAborted()
      const child = ctx.subprocess.spawn({
        argv: [config.python, '-B', HELPER, operation, cli],
        cwd: config.runtimeRoot,
        stdio: { stdin: 'ignore', stdout: { maxBytes: operation === 'models' ? MODEL_OUTPUT_BYTES : 64 },
          stderr: { maxBytes: 1 } },
        graceMs: config.disposeGraceMs,
        env: { PYTHONPATH: config.runtimeRoot, ...config.env },
        signal,
      })
      const result = await child.done
      if (signal.aborted) await child.waitForExit(AbortSignal.timeout(config.disposeGraceMs))
      const output = child.collected.stdout?.readFrom(0)
      if (result.exitCode === 0 && !signal.aborted && output?.lossy === false) return output.text.trim()
    } catch {
      // Never relay subprocess diagnostics or account data to the client or logs.
    }
  }

  async function invoke(operation: 'status' | 'login', cli: Cli, signal?: AbortSignal): Promise<string> {
    const value = await runHelper(operation, cli, signal)
    return value && (statuses.has(value) || (operation === 'login' && value === 'closed')) ? value : 'unknown'
  }

  async function readCatalog(): Promise<z.infer<typeof modelReply>> {
    const value = await runHelper('models', 'codex')
    if (value) {
      try {
        return modelReply.parse(JSON.parse(value))
      } catch { /* Do not forward the raw CLI output. */ }
    }
    return { status: 'unavailable' }
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
      if ((cli !== 'codex' && cli !== 'codebuddy')
        || (operation !== 'status' && operation !== 'login' && operation !== 'models')
        || [...query].length !== 2) return response('unknown', 400)
      if (signingIn.has(cli)) return response('running', operation === 'login' ? 409 : 200)
      if (operation === 'models') {
        if (cli !== 'codex') return response('unsupported')
        catalog ??= readCatalog().finally(() => { catalog = undefined })
        return Response.json(await catalog, { headers: { 'cache-control': 'no-store' } })
      }
      if (operation === 'login') {
        signingIn.add(cli)
        try {
          await checking.get(cli)
          if (cli === 'codex') await catalog
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
