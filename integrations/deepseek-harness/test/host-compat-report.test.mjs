import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
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
  assert.deepEqual(result, { classification: 'SAME_ARTIFACTS', changed_packages: [], minimum_gate: 'fast-smoke' })
})

test('Host shell and imported tool changes are classified separately', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  writeFileSync(join(fixture.dsh, 'lib', 'index.js'), 'export const value = 2\n')
  const shell = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.equal(compareHostSnapshots(before, shell).classification, 'HOST_SHELL_CHANGED')
  writeFileSync(join(fixture.tools, 'lib', 'index.js'), 'export const value = 2\n')
  const imported = compareHostSnapshots(before, collectHostSnapshot(fixture.host, fixture.plugin))
  assert.equal(imported.classification, 'IMPORTED_SURFACE_CHANGED')
  assert.deepEqual(imported.changed_packages, ['@deepseek-ai/dsh', '@deepseek-ai/dsh-tools'])
})

test('missing and conflicting installed packages fail closed', t => {
  const fixture = makeFixture(t)
  const before = collectHostSnapshot(fixture.host, fixture.plugin)
  rmSync(fixture.tools, { recursive: true })
  const missing = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(missing.issues, [{ package: '@deepseek-ai/dsh-tools', reason: 'missing' }])
  assert.equal(compareHostSnapshots(before, missing).classification, 'BLOCKED_INPUT')
  fixture.addPackage(fixture.plugin, 'dsh-tools', '0.2.1-rc.2')
  fixture.addPackage(fixture.host, 'dsh-tools', '0.3.0')
  const ambiguous = collectHostSnapshot(fixture.host, fixture.plugin)
  assert.deepEqual(ambiguous.issues, [{ package: '@deepseek-ai/dsh-tools', reason: 'ambiguous-installed-variants' }])
})

test('runner declaration must match the installed official Host', t => {
  const fixture = makeFixture(t)
  writeFileSync(join(fixture.host, 'package.json'), JSON.stringify({ dependencies: { '@deepseek-ai/dsh': '0.3.0' } }))
  assert.deepEqual(collectHostSnapshot(fixture.host, fixture.plugin).issues,
    [{ package: 'host-runner', reason: 'declared-host-version-mismatch' }])
})
