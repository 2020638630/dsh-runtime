import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const [outputDirectory] = process.argv.slice(2)
if (!outputDirectory || process.argv.length !== 3 || !process.env.npm_execpath) {
  throw new Error('Usage: pnpm run pack:desktop-rc1 <existing-output-directory>')
}

const source = fileURLToPath(new URL('..', import.meta.url))
const destination = realpathSync(outputDirectory)
const manifest = JSON.parse(readFileSync(join(source, 'package.json'), 'utf8'))
const hostVersion = '0.2.2-rc.1'
const pluginVersion = '0.1.0-rc.34'

// Shared runtime packages must resolve from the Desktop host. Installing copies
// into its Profile can replace core services even while this bundle is disabled.
manifest.version = pluginVersion
manifest.engines.dsh = hostVersion
manifest.peerDependencies = {
  '@deepseek-ai/dsh-brand': hostVersion,
  '@deepseek-ai/dsh-subagent': hostVersion,
  '@deepseek-ai/dsh-subprocess': hostVersion,
  '@deepseek-ai/dsh-tools': hostVersion,
}
manifest.dependencies = { zod: manifest.dependencies.zod }
delete manifest.devDependencies
delete manifest.scripts

const archive = `dsh-runtime-harness-plugin-${pluginVersion}.tgz`
if (existsSync(join(destination, archive))) throw new Error(`Archive already exists: ${archive}`)

const stage = mkdtempSync(join(destination, 'dsh-runtime-desktop-pack-'))
try {
  for (const file of manifest.files) cpSync(join(source, file), join(stage, file), { recursive: true })
  // pnpm rejects CRLF shebangs, which can come from a Windows Git checkout.
  for (const bin of Object.values(manifest.bin)) {
    const stagedBin = join(stage, bin)
    writeFileSync(stagedBin, readFileSync(stagedBin, 'utf8').replaceAll('\r\n', '\n'))
  }
  writeFileSync(join(stage, 'package.json'), JSON.stringify(manifest, null, 2) + '\n')
  const result = spawnSync(process.execPath, [process.env.npm_execpath, 'pack', '--pack-destination', destination], {
    cwd: stage,
    stdio: 'inherit',
  })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`Could not pack Desktop bundle (exit ${result.status ?? result.signal})`)
} finally {
  const resolvedStage = realpathSync(stage)
  if (dirname(resolvedStage) !== destination) throw new Error('Desktop package staging path escaped its destination')
  rmSync(resolvedStage, { recursive: true })
}
