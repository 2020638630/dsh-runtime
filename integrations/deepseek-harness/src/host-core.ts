/** Mount governance and two fixed-purpose providers after worker READY. */
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-subagent'
import type {} from '@deepseek-ai/dsh-subprocess'
import { createGovernedProvider } from './provider.ts'
import { createRuntimeLauncher, type RuntimeLauncherConfig } from './runtime-launcher.ts'
import { GovernanceBridge, type BridgeProcessConfig } from './governance/bridge.ts'
import { governancePolicyPinProjectionDefinition } from './governance/session-pin.ts'

export interface HostCoreConfig {
  readonly governance: BridgeProcessConfig
  readonly runtime: Omit<RuntimeLauncherConfig, 'spawn'>
}

/** Register nothing runnable until the Python worker confirms policy identity. */
export async function mountHostCore(ctx: Context, config: HostCoreConfig): Promise<() => Promise<void>> {
  const unregisterPin = ctx.sessionProjections.register(governancePolicyPinProjectionDefinition)
  let bridge: GovernanceBridge | undefined
  const providerDisposers: Array<() => void> = []
  let disposed = false
  async function dispose(): Promise<void> {
    if (disposed) return
    disposed = true
    let firstError: unknown
    for (const release of providerDisposers.reverse()) {
      try { release() } catch (error) { firstError ??= error }
    }
    try { await bridge?.dispose() } catch (error) { firstError ??= error }
    try { unregisterPin() } catch (error) { firstError ??= error }
    if (firstError !== undefined) throw firstError
  }
  try {
    bridge = new GovernanceBridge(spec => ctx.subprocess.spawn(spec), ctx.sessionProjections, config.governance)
    await bridge.waitForReady()
    const launch = createRuntimeLauncher({ ...config.runtime, spawn: spec => ctx.subprocess.spawn(spec) })
    providerDisposers.push(ctx.subagents.registerProvider(createGovernedProvider('repository_inspection', bridge, launch)))
    providerDisposers.push(ctx.subagents.registerProvider(createGovernedProvider('repository_change', bridge, launch)))
    return dispose
  } catch (error) {
    try { await dispose() } catch (cleanupError) {
      throw new AggregateError([error, cleanupError], 'host core startup and cleanup failed')
    }
    throw error
  }
}
