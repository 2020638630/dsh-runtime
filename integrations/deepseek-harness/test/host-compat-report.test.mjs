import assert from 'node:assert/strict'
import { copyFileSync, mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { collectHostSnapshot, compareHostSnapshots } from '../scripts/host-compat-report.mjs'

function makeFixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'dsh-host-compat-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const host = join(root, 'host')
  const plugin = join(root, 'plugin')
  const source = join(plugin, 'src')
  mkdirSync(host, { recursive: true })
  mkdirSync(source, { recursive: true })
  writeFileSync(join(source, 'index.ts'), "import { defineTool } from '@deepseek-ai/dsh-tools'\n")
  writeFileSync(join(host, 'package.json'), JSON.stringify({ dependencies: { '@deepseek-ai/dsh': '0.2.1-rc.2' } }))
  writeFileSync(join(host, 'pnpm-lock.yaml'), 'lockfileVersion: 9\n')
  function addPackage(base, name, version, implementation = 'export const value = 1\n') {
    const path = join(base, 'node_modules', '@deepseek-ai', name)
    mkdirSync(join(path, 'lib'), { recursive: true })
    writeFileSync(join(path, 'package.json'), JSON.stringify({ name: `@deepseek-ai/${name}`, version }))
    writeFileSync(join(path, 'lib', 'index.js'), implementation)
    return path
  }
  const dsh = addPackage(host, 'dsh', '0.2.1-rc.2')
  const tools = addPackage(plugin, 'dsh-tools', '0.2.1-rc.2')
  return { host, plugin, dsh, tools, addPackage }
}

test('identical Host artifacts need only the fast gate', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(before.issues, [])
  assert.equal(before.host_version, '0.2.1-rc.2')
  const result = compareHostSnapshots(before, collectHostSnapshot(fixture.host, fixture.plugin))
  assert.deepEqual(result, { classification: 'SAME_ARTIFACTS', changed_packages: [],
    artifact_changed_packages: [], metadata_only_packages: [], minimum_gate: 'fast-smoke' })
})

test('Host shell and imported tool changes are classified separately', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  writeFileSync(join(fixture.dsh, 'lib', 'index.js'), 'export const value = 2\n')
  const shell = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.equal(compareHostSnapshots(before, shell).classification, 'HOST_SHELL_CHANGED')
  writeFileSync(join(fixture.tools, 'lib', 'index.js'), 'export const value = 2\n')
  const imported = compareHostSnapshots(before, collectHostSnapshot(fixture.host, fixture.plugin))
  assert.equal(imported.classification, 'IMPORTED_ARTIFACT_CHANGED')
  assert.deepEqual(imported.changed_packages, ['@deepseek-ai/dsh', '@deepseek-ai/dsh-tools'])
  assert.deepEqual(imported.artifact_changed_packages, ['@deepseek-ai/dsh', '@deepseek-ai/dsh-tools'])
})

test('version-only package metadata does not imply imported code changed', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  writeFileSync(join(fixture.tools, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.2.1-rc.3' }))
  const result = compareHostSnapshots(before, collectHostSnapshot(fixture.host, fixture.plugin))
  assert.equal(result.classification, 'PACKAGE_METADATA_CHANGED')
  assert.deepEqual(result.metadata_only_packages, ['@deepseek-ai/dsh-tools'])
  assert.deepEqual(result.artifact_changed_packages, [])
  assert.equal(result.minimum_gate, 'focused-or-higher')
})

test('installed package digest detects bin and non-lib entry file changes', t => {
  const fixture = makeFixture(t)
  mkdirSync(join(fixture.dsh, 'bin'))
  writeFileSync(join(fixture.dsh, 'bin', 'cli.js'), 'console.log(1)\n')
  writeFileSync(join(fixture.tools, 'entry.js'), 'export const entry = 1\n')
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  writeFileSync(join(fixture.dsh, 'bin', 'cli.js'), 'console.log(2)\n')
  assert.equal(compareHostSnapshots(before, collectHostSnapshot(fixture.host, fixture.plugin)).classification, 'HOST_SHELL_CHANGED')
  writeFileSync(join(fixture.tools, 'entry.js'), 'export const entry = 2\n')
  assert.equal(compareHostSnapshots(before, collectHostSnapshot(fixture.host, fixture.plugin)).classification, 'IMPORTED_ARTIFACT_CHANGED')
})

test('import inventory reads source syntax without comments or string false positives', t => {
  const fixture = makeFixture(t)
  const src = join(fixture.plugin, 'src')
  writeFileSync(join(src, 'panel.tsx'), "export { x } from '@deepseek-ai/dsh-ui/subpath'\n")
  writeFileSync(join(src, 'dynamic.js'), "const x = await import(`@deepseek-ai/dsh-dynamic`)\nconst y = require('@deepseek-ai/dsh-required')\nconst z = await import('@deepseek-ai/dsh-attributes', { with: { type: 'json' } })\n")
  writeFileSync(join(src, 'noise.ts'), "// from '@deepseek-ai/dsh-fake'\nconst text = \"from '@deepseek-ai/dsh-fake2'\"\n")
  for (const name of ['dsh-ui', 'dsh-dynamic', 'dsh-required', 'dsh-attributes']) fixture.addPackage(fixture.plugin, name, '1.0.0')
  const snapshot = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(snapshot.issues, [])
  assert.deepEqual(snapshot.imported_packages, ['@deepseek-ai/dsh', '@deepseek-ai/dsh-attributes', '@deepseek-ai/dsh-dynamic',
    '@deepseek-ai/dsh-required', '@deepseek-ai/dsh-tools', '@deepseek-ai/dsh-ui'])
})

test('missing and conflicting installed packages fail closed', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  rmSync(fixture.tools, { recursive: true })
  const missing = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(missing.issues, [{ package: '@deepseek-ai/dsh-tools', reason: 'missing', versions: [] }])
  assert.equal(compareHostSnapshots(before, missing).classification, 'BLOCKED_INPUT')
  fixture.addPackage(fixture.plugin, 'dsh-tools', '0.2.1-rc.2')
  fixture.addPackage(fixture.host, 'dsh-tools', '0.3.0')
  writeFileSync(join(fixture.host, 'package.json'), JSON.stringify({ dependencies: {
    '@deepseek-ai/dsh': '0.2.1-rc.2', '@deepseek-ai/dsh-tools': '0.3.0' } }))
  const ambiguous = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(ambiguous.issues, [{ package: '@deepseek-ai/dsh-tools', reason: 'ambiguous-installed-variants',
    versions: ['0.2.1-rc.2', '0.3.0'] }])
})

test('a stale pnpm store entry does not conflict with the directly linked package', t => {
  const fixture = makeFixture(t)
  const stale = join(fixture.plugin, 'node_modules', '.pnpm', '@deepseek-ai+dsh-tools@0.1.0',
    'node_modules', '@deepseek-ai', 'dsh-tools')
  mkdirSync(join(stale, 'lib'), { recursive: true })
  writeFileSync(join(stale, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.1.0' }))
  writeFileSync(join(stale, 'lib', 'index.js'), 'export const value = 0\n')
  const snapshot = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(snapshot.issues, [])
  assert.equal(snapshot.packages['@deepseek-ai/dsh-tools'].version, '0.2.1-rc.2')
})

test('a stale Host store entry does not conflict with a linked Host dependency', t => {
  const fixture = makeFixture(t)
  const virtual = join(fixture.host, 'node_modules', '.pnpm', '@deepseek-ai+dsh@0.2.1-rc.2', 'node_modules')
  const installedHost = join(virtual, '@deepseek-ai', 'dsh')
  mkdirSync(join(installedHost, 'lib'), { recursive: true })
  writeFileSync(join(installedHost, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh', version: '0.2.1-rc.2',
    dependencies: { '@deepseek-ai/dsh-tools': '0.2.1-rc.2' } }))
  writeFileSync(join(installedHost, 'lib', 'index.js'), 'export const value = 1\n')
  rmSync(fixture.dsh, { recursive: true })
  symlinkSync(installedHost, fixture.dsh, process.platform === 'win32' ? 'junction' : 'dir')
  const linkedTool = join(virtual, '@deepseek-ai', 'dsh-tools')
  mkdirSync(join(linkedTool, 'lib'), { recursive: true })
  writeFileSync(join(linkedTool, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.2.1-rc.2' }))
  writeFileSync(join(linkedTool, 'lib', 'index.js'), 'export const value = 1\n')
  const stale = join(fixture.host, 'node_modules', '.pnpm', '@deepseek-ai+dsh-tools@0.1.0',
    'node_modules', '@deepseek-ai', 'dsh-tools')
  mkdirSync(join(stale, 'lib'), { recursive: true })
  writeFileSync(join(stale, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.1.0' }))
  writeFileSync(join(stale, 'lib', 'index.js'), 'export const value = 0\n')
  const snapshot = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(snapshot.issues, [])
  writeFileSync(join(linkedTool, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.3.0' }))
  assert.deepEqual(collectHostSnapshot(fixture.host, fixture.plugin).issues,
    [{ package: '@deepseek-ai/dsh-tools', reason: 'ambiguous-installed-variants', versions: ['0.2.1-rc.2', '0.3.0'] }])
})

test('unreachable stale Host store variants are ignored when Profile resolves one package', t => {
  const fixture = makeFixture(t)
  for (const version of ['0.1.0', '0.3.0']) {
    const stale = join(fixture.host, 'node_modules', '.pnpm', `@deepseek-ai+dsh-tools@${version}`,
      'node_modules', '@deepseek-ai', 'dsh-tools')
    mkdirSync(stale, { recursive: true })
    writeFileSync(join(stale, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version }))
  }
  assert.deepEqual(collectHostSnapshot(fixture.host, fixture.plugin).issues, [])
})

test('installed plugin inventory may use a separate source root for imports', t => {
  const fixture = makeFixture(t)
  const installed = join(fixture.plugin, '..', 'installed-profile')
  fixture.addPackage(installed, 'dsh-tools', '0.2.1-rc.2')
  const snapshot = collectHostSnapshot(fixture.host, installed, fixture.plugin)
  assert.deepEqual(snapshot.issues, [])
  assert.deepEqual(snapshot.imported_packages, ['@deepseek-ai/dsh', '@deepseek-ai/dsh-tools'])
  assert.equal(snapshot.packages['@deepseek-ai/dsh-tools'].version, '0.2.1-rc.2')
})

test('Windows-shortened pnpm store names resolve through the package directory', t => {
  const fixture = makeFixture(t)
  const installed = join(fixture.plugin, '..', 'short-name-profile')
  mkdirSync(installed, { recursive: true })
  writeFileSync(join(installed, 'package.json'), JSON.stringify({ dependencies: { '@dsh-runtime/harness-plugin': '1.0.0' } }))
  const virtual = join(installed, 'node_modules', '.pnpm', '@dsh-runtime+harness-plugin_opaquehash', 'node_modules')
  const wrapper = join(virtual, '@dsh-runtime', 'harness-plugin')
  mkdirSync(wrapper, { recursive: true })
  writeFileSync(join(wrapper, 'package.json'), JSON.stringify({ name: '@dsh-runtime/harness-plugin', version: '1.0.0',
    dependencies: { '@deepseek-ai/dsh-tools': '0.2.1-rc.2' } }))
  const direct = join(installed, 'node_modules', '@dsh-runtime', 'harness-plugin')
  mkdirSync(dirname(direct), { recursive: true })
  symlinkSync(wrapper, direct, process.platform === 'win32' ? 'junction' : 'dir')
  const packageRoot = join(installed, 'node_modules', '.pnpm', '@deepseek-ai+dsh-to_opaquehash',
    'node_modules', '@deepseek-ai', 'dsh-tools')
  mkdirSync(join(packageRoot, 'lib'), { recursive: true })
  writeFileSync(join(packageRoot, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.2.1-rc.2' }))
  writeFileSync(join(packageRoot, 'lib', 'index.js'), 'export const value = 1\n')
  const stale = join(installed, 'node_modules', '.pnpm', '@deepseek-ai+dsh-tools@0.1.0',
    'node_modules', '@deepseek-ai', 'dsh-tools')
  mkdirSync(stale, { recursive: true })
  writeFileSync(join(stale, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version: '0.1.0' }))
  mkdirSync(join(virtual, '@deepseek-ai'), { recursive: true })
  symlinkSync(packageRoot, join(virtual, '@deepseek-ai', 'dsh-tools'), process.platform === 'win32' ? 'junction' : 'dir')
  const snapshot = collectHostSnapshot(fixture.host, installed, fixture.plugin)
  assert.deepEqual(snapshot.issues, [])
  assert.equal(snapshot.packages['@deepseek-ai/dsh-tools'].version, '0.2.1-rc.2')
})

test('unreachable plugin store entries do not count as installed packages', t => {
  const fixture = makeFixture(t)
  const installed = join(fixture.plugin, '..', 'stale-profile')
  mkdirSync(installed, { recursive: true })
  writeFileSync(join(installed, 'package.json'), JSON.stringify({ dependencies: {} }))
  for (const version of ['0.2.1-rc.2', '0.2.1-rc.3']) {
    const stale = join(installed, 'node_modules', '.pnpm', `@deepseek-ai+dsh-tools@${version}`,
      'node_modules', '@deepseek-ai', 'dsh-tools')
    mkdirSync(stale, { recursive: true })
    writeFileSync(join(stale, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version }))
  }
  const snapshot = collectHostSnapshot(fixture.host, installed, fixture.plugin)
  assert.deepEqual(snapshot.issues, [{ package: '@deepseek-ai/dsh-tools', reason: 'missing', versions: [] }])
  assert.equal(compareHostSnapshots(collectHostSnapshot(fixture.host, fixture.plugin), snapshot).classification, 'BLOCKED_INPUT')
})

test('two plugin-reachable package versions remain ambiguous', t => {
  const fixture = makeFixture(t)
  const installed = join(fixture.plugin, '..', 'mixed-profile')
  mkdirSync(installed, { recursive: true })
  writeFileSync(join(installed, 'package.json'), JSON.stringify({ dependencies: {
    '@dsh-runtime/adapter-a': '1.0.0', '@dsh-runtime/adapter-b': '1.0.0' } }))
  for (const [adapter, version] of [['adapter-a', '0.2.1-rc.2'], ['adapter-b', '0.2.1-rc.3']]) {
    const virtual = join(installed, 'node_modules', '.pnpm', `@dsh-runtime+${adapter}_opaquehash`, 'node_modules')
    const wrapper = join(virtual, '@dsh-runtime', adapter)
    mkdirSync(wrapper, { recursive: true })
    writeFileSync(join(wrapper, 'package.json'), JSON.stringify({ name: `@dsh-runtime/${adapter}`, version: '1.0.0',
      dependencies: { '@deepseek-ai/dsh-tools': version } }))
    const tool = join(virtual, '@deepseek-ai', 'dsh-tools')
    mkdirSync(tool, { recursive: true })
    writeFileSync(join(tool, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', version }))
    writeFileSync(join(tool, 'index.js'), `export const version = '${version}'\n`)
    const direct = join(installed, 'node_modules', '@dsh-runtime', adapter)
    mkdirSync(dirname(direct), { recursive: true })
    symlinkSync(wrapper, direct, process.platform === 'win32' ? 'junction' : 'dir')
  }
  assert.deepEqual(collectHostSnapshot(fixture.host, installed, fixture.plugin).issues,
    [{ package: '@deepseek-ai/dsh-tools', reason: 'ambiguous-installed-variants',
      versions: ['0.2.1-rc.2', '0.2.1-rc.3'] }])
})

test('runner declaration must match the installed official Host', t => {
  const fixture = makeFixture(t)
  writeFileSync(join(fixture.host, 'package.json'), JSON.stringify({ dependencies: { '@deepseek-ai/dsh': '0.3.0' } }))
  assert.deepEqual(collectHostSnapshot(fixture.host, fixture.plugin).issues,
    [{ package: 'host-runner', reason: 'declared-host-version-mismatch' }])
})

test('missing pnpm lockfile and old snapshot schema stop comparison', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  rmSync(join(fixture.host, 'pnpm-lock.yaml'))
  const after = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.ok(after.issues.some(issue => issue.reason === 'missing-pnpm-lockfile'))
  assert.equal(compareHostSnapshots(before, after).classification, 'BLOCKED_INPUT')
  assert.equal(compareHostSnapshots({ ...before, schema_version: 2 }, before).classification, 'BLOCKED_INPUT')
})

test('CLI executes through a directory junction rather than silently exiting', t => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-host-compat-cli-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const link = join(root, 'scripts-link')
  symlinkSync(join(dirname(dirname(fileURLToPath(import.meta.url))), 'scripts'), link,
    process.platform === 'win32' ? 'junction' : 'dir')
  const run = spawnSync(process.execPath, [join(link, 'host-compat-report.mjs')], { encoding: 'utf8' })
  if (run.error?.code === 'EPERM') return t.skip('sandbox denied child process; rerun outside process sandbox')
  assert.ifError(run.error)
  assert.equal(run.status, 2)
  assert.match(run.stderr, /Usage: node host-compat-report\.mjs/u)
})

test('CLI explains missing TypeScript development dependency', t => {
  const fixture = makeFixture(t)
  const isolated = mkdtempSync(join(tmpdir(), 'dsh-host-compat-isolated-'))
  t.after(() => rmSync(isolated, { recursive: true, force: true }))
  const script = join(isolated, 'host-compat-report.mjs')
  copyFileSync(join(dirname(dirname(fileURLToPath(import.meta.url))), 'scripts', 'host-compat-report.mjs'), script)
  const run = spawnSync(process.execPath, [script, '--host', fixture.host, '--plugin', fixture.plugin], { encoding: 'utf8' })
  if (run.error?.code === 'EPERM') return t.skip('sandbox denied child process; rerun outside process sandbox')
  assert.ifError(run.error)
  assert.equal(run.status, 2)
  assert.match(run.stderr, /typescript is required for the source import inventory/u)
})
