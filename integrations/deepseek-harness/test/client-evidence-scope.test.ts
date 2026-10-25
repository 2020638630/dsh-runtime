import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'

const source = readFileSync(join(import.meta.dirname, '..', '..', 'src', 'client.js'), 'utf8')

function render(tab: string, changes: Record<string, unknown>, scope?: Record<string, unknown>,
  relocation?: { status: 'verified_copy'; createdAt: string }): string {
  let registered: ((props: Record<string, unknown>) => unknown) | undefined
  const react = {
    createElement: (type: unknown, props: unknown, ...children: unknown[]) => ({ type, props, children }),
    useState: (() => {
      let index = 0
      return (initial: unknown) => {
        const values = [
          { manifest: {
            status: 'completed', duration_ms: 1, workspace_changes: changes,
            evidence_scope: scope,
            verification: { verdict: 'PASS', evidence_text: 'model report' },
            execution_trajectory: { status: 'available', turns_used: null },
            audit: { status: 'settled', call_id: 'id', stdout_sha256: 'hash' },
          }, diff: 'patch text', relocation }, true, tab, Date.now(),
        ]
        return [values[index++] ?? initial, () => {}]
      }
    })(),
    useEffect: () => {},
  }
  let plugin: { apply: (ctx: unknown) => void } | undefined
  runInNewContext(source, {
    window: { __ModuleLoader__: { load: (registration: { factory: (require: (id: string) => unknown) => unknown }) => {
      plugin = registration.factory(id => id === 'react' ? react : { createPortal: (node: unknown) => node }) as typeof plugin
    } } },
    document: { body: {} }, Date, AbortController, URLSearchParams, setInterval, clearInterval,
  })
  plugin?.apply({ slots: { inject: (_: string, callback: () => unknown) => callback(),
    register: (_: unknown, component: typeof registered) => { registered = component } } })
  assert.ok(registered)
  const tree = registered({ phase: 'result', sessionId: 'session', block: {
    content: [{ type: 'text', text: 'started governed DSH Runtime task 00000000-0000-4000-8000-000000000001' }],
  } })
  const strings: string[] = []
  const visit = (value: unknown): void => {
    if (typeof value === 'string') strings.push(value)
    else if (Array.isArray(value)) value.forEach(visit)
    else if (value && typeof value === 'object' && 'children' in value) visit(value.children)
  }
  visit(tree)
  return strings.join('\n')
}

test('drawer separates model verdict from bounded snapshot and uncertain attribution', () => {
  const changes = {
    source: 'workspace_pre_post_snapshot_delta', baseline_compared: true,
    observation_boundary: 'window_observed_changes',
    added_files: ['one.txt'], modified_files: [], deleted_files: [],
    scope_exclusions: ['.git/'], patch_applicable: true,
  }
  const scope = { change_attribution: 'not_established_shared_workspace' }
  const text = render('changes', changes, scope)
  assert.match(text, /模型审查判决：PASS/u)
  assert.match(text, /文件范围证据：运行前后快照观察/u)
  assert.match(text, /变动归属：未证明/u)
  assert.match(text, /新增：one\.txt/u)
  assert.match(render('audit', changes, scope), /判决范围：模型报告/u)
})

test('drawer identifies a verified historical copy without presenting its hashes as task proof', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const text = render('audit', changes, undefined,
    { status: 'verified_copy', createdAt: '2026-10-25T00:00:00.000Z' })
  assert.match(text, /历史证据副本/u)
  assert.match(text, /不证明原始任务或审查正确/u)
})

test('drawer does not present a file list as confirmed without snapshot metadata', () => {
  const text = render('changes', {
    added_files: ['unverified.txt'], modified_files: [], deleted_files: [],
  })
  assert.match(text, /文件范围证据：不可用/u)
  assert.match(text, /变动归属：未知/u)
  assert.doesNotMatch(text, /新增：unverified\.txt/u)
})
