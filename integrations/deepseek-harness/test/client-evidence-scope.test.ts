import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'

const source = readFileSync(join(import.meta.dirname, '..', '..', 'src', 'client.js'), 'utf8')
type View = (props: Record<string, unknown>) => unknown
type Element = { type: unknown; props: Record<string, unknown> | null; children: unknown[] }
const createElement = (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): Element =>
  ({ type, props, children })
const startedProps = { phase: 'result', sessionId: 'session', block: {
  content: [{ type: 'text', text: 'started governed DSH Runtime task 00000000-0000-4000-8000-000000000001' }],
} }

function loadViews(react: unknown, configForms?: unknown, windowLocation: object = {}): Map<string, View> {
  const views = new Map<string, View>()
  let plugin: { apply: (ctx: unknown) => void } | undefined
  runInNewContext(source, {
    window: { location: windowLocation, __ModuleLoader__: { load: (registration: { factory: (require: (id: string) => unknown) => unknown }) => {
      plugin = registration.factory(id => id === 'react' ? { useRef: () => ({ current: null }), ...(react as object) }
        : { createPortal: (node: unknown) => node }) as typeof plugin
    } } },
    document: { body: {} }, Date, AbortController, URLSearchParams, setInterval, clearInterval,
  })
  const slots = { inject: (_: string, callback: () => unknown) => callback(),
    register: (options: { name: string }, component: View) => { views.set(options.name, component) } }
  plugin?.apply({ slots, inject: (_: string[], callback: (ctx: unknown) => unknown) => {
    if (configForms) callback({ configForms, slots })
  } })
  return views
}

function nodes(value: unknown): Element[] {
  if (Array.isArray(value)) return value.flatMap(nodes)
  if (value && typeof value === 'object' && 'children' in value) {
    const node = value as Element
    return [node, ...nodes(node.children)]
  }
  return []
}

test('running card announces the phase without announcing the elapsed time on every tick', () => {
  const now = Date.now()
  const props = { ...startedProps, block: { ...startedProps.block, time: now - 20_000 } }
  const progress = {
    phase: { role: 'reviewer', adapter: 'codex' },
    activity: { adapter: 'codex', kind: 'tool', tool: 'commandExecution', status: 'completed', atMs: now - 4_000 },
  }
  let index = 0
  const values = ['waiting', false, 'trajectory', now, progress]
  const view = loadViews({
    createElement,
    useState: () => [values[index++], () => {}],
    useEffect: () => {},
  }).get('tool.call.toolview')!
  const elements = nodes(view(props))
  const strings = elements.flatMap(node => node.children.filter(child => typeof child === 'string'))
  assert.equal(elements.find(node => node.props?.role === 'status')?.children.join(''), '审查阶段 · Codex')
  assert.ok(strings.includes(' · 20 秒'))
  assert.ok(strings.includes('最近事件 · Codex · 命令 · 已完成 · 4 秒前'))
  assert.ok(!strings.includes('查看证据'))
})

type MissingEvidence = 'aborted' | 'error' | 'unavailable' | 'read-error'
function renderTree(tab: string, changes: Record<string, unknown>, scope?: Record<string, unknown>,
  relocation?: { status: 'verified_copy'; createdAt: string }, modelObservations?: unknown,
  terminal?: Record<string, unknown> | MissingEvidence, diff = 'patch text'): Element {
  const react = {
    createElement,
    useState: (() => {
      let index = 0
      return (initial: unknown) => {
        const values = [
          typeof terminal === 'string' ? terminal : { manifest: {
            status: 'completed', duration_ms: 1, workspace_changes: changes,
            task_kind: 'repository_change', model_observations: modelObservations,
            evidence_scope: scope,
            verification: { verdict: 'PASS', evidence_text: 'model report' },
            execution_trajectory: { status: 'available', turns_used: null },
            audit: { status: 'settled', call_id: 'id', stdout_sha256: 'hash' },
            ...terminal,
          }, diff, relocation }, true, tab, Date.now(),
        ]
        return [values[index++] ?? initial, () => {}]
      }
    })(),
    useEffect: () => {},
  }
  const view = loadViews(react).get('tool.call.toolview')!
  return view(startedProps) as Element
}

function render(...args: Parameters<typeof renderTree>): string {
  const strings: string[] = []
  const visit = (value: unknown): void => {
    if (typeof value === 'string') strings.push(value)
    else if (Array.isArray(value)) value.forEach(visit)
    else if (value && typeof value === 'object' && 'children' in value) visit(value.children)
  }
  visit(renderTree(...args))
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

test('drawer separates requested and returned model by role and degrades old or invalid evidence', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const models = {
    version: 1, source: 'codex_thread_start',
    entries: [
      { role: 'worker', adapter: 'codex', invocation_index: 1,
        requested_model: 'worker-request', reported_model: 'worker-return' },
      { role: 'reviewer', adapter: 'codex', invocation_index: 2,
        requested_model: null, reported_model: null },
    ],
  }
  const text = render('trajectory', changes, undefined, undefined, models)
  assert.match(text, /执行阶段模型：Codex · 请求 worker-request · CLI 启动返回 worker-return（与请求不同）/u)
  assert.match(text, /审查阶段模型：Codex · 请求 CLI 默认 · CLI 启动返回 未知/u)
  const old = render('trajectory', changes)
  assert.match(old, /执行阶段模型：未记录/u)
  assert.match(old, /审查阶段模型：未记录/u)
  const invalid = render('trajectory', changes, undefined, undefined, {
    ...models, entries: [{ ...models.entries[0], reported_model: '<script>' }],
  })
  assert.match(invalid, /执行阶段模型：未记录/u)
  assert.doesNotMatch(invalid, /<script>/u)
})

test('drawer labels CodeBuddy JSON evidence and unknown separately from Codex', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const worker = { role: 'worker', adapter: 'codebuddy', invocation_index: 1,
    requested_model: null, reported_model: 'provider/model', source: 'codebuddy_json_assistant' }
  const reviewer = { role: 'reviewer', adapter: 'codex', invocation_index: 2,
    requested_model: null, reported_model: 'review-return', source: 'codex_thread_start' }
  const draw = (workerEvidence: unknown) => render('trajectory', changes, undefined, undefined,
    { version: 2, entries: [workerEvidence, reviewer] })
  assert.match(draw(worker), /执行阶段模型：CodeBuddy · 请求 CLI 默认 · CLI JSON 报告 provider\/model/u)
  assert.match(draw(worker), /审查阶段模型：Codex · 请求 CLI 默认 · CLI 启动返回 review-return/u)
  assert.match(draw({ ...worker, requested_model: 'worker-request', reported_model: null, source: 'unobserved' }),
    /执行阶段模型：CodeBuddy · 请求 worker-request · CLI 报告 未知/u)
  assert.match(draw({ ...worker, source: 'codex_thread_start' }), /执行阶段模型：未记录/u)
})

test('terminal guidance distinguishes review failure, unavailable evidence and an inspection', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const status = 'failed'
  const run_id = 'dsh-runtime-00000000-0000-4000-8000-000000000001'
  const draw = (terminal: Record<string, unknown> | MissingEvidence) =>
    render('audit', changes, undefined, undefined, undefined, terminal)
  const fail = draw({ status, run_id, verification: { verdict: 'FAIL', evidence_text: 'review basis' } })
  assert.match(fail, /模型审查未通过/u)
  assert.ok(fail.includes(run_id) && fail.includes('调用 ID：id') && fail.includes('review basis'))
  for (const [invocation_binding, text] of [
    ['missing', '缺少审查调用记录'], ['invalid', '审查调用证据未通过绑定校验'],
    ['matched', '现有证据无法形成有效的审查判决'], [undefined, '现有证据无法形成有效的审查判决'],
  ] as const) {
    assert.ok(draw({ status, verification: { verdict: 'UNAVAILABLE', invocation_binding } }).includes(text))
  }
  for (const state of ['aborted', 'error', 'unavailable', 'read-error'] as const) {
    assert.match(draw(state), /无法确认文件是否发生变动/u)
    assert.doesNotMatch(draw(state), /BLOCKED|查看证据/u)
  }
  assert.doesNotMatch(draw({ task_kind: 'repository_inspection', verification: { verdict: 'UNAVAILABLE' } }), /现有证据无法/u)
})

test('overview keeps task, verdict, trajectory and audit states independent', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const overview = (terminal: Record<string, unknown>) => nodes(renderTree('trajectory', changes,
    undefined, undefined, undefined, terminal)).filter(node => node.type === 'dt' || node.type === 'dd')
    .map(node => node.children.join(''))
  assert.deepEqual(overview({ status: 'timed_out', verification: { verdict: 'UNAVAILABLE' },
    execution_trajectory: { status: 'incomplete' }, audit: { status: 'unavailable' } }),
  ['任务状态', '运行超时', '模型审查判决', '无法确认', '轨迹状态', '不完整', '审计状态', '不可用'])
  assert.deepEqual(overview({ task_kind: 'repository_inspection', verification: { verdict: 'UNAVAILABLE' } }),
    ['任务状态', '已完成', '模型审查判决', '不适用', '轨迹状态', '可用', '审计状态', '已结算'])
})

test('long patches and audit details are collapsed by default', () => {
  const changes = {
    source: 'workspace_pre_post_snapshot_delta', baseline_compared: true,
    observation_boundary: 'window_observed_changes',
    added_files: ['new.txt'], modified_files: [], deleted_files: [],
  }
  const text = 'x'.repeat(200001)
  const patch = nodes(renderTree('changes', changes, undefined, undefined, undefined, undefined, text))
    .find(node => node.type === 'details')!
  assert.equal(patch.props?.open, undefined)
  assert.equal(nodes(patch).find(node => node.type === 'pre')?.children[0], text.slice(0, 200000))
  assert.match(nodes(patch).find(node => node.type === 'p')?.children.join('') ?? '', /仅展示/u)
  const auditDetails = nodes(renderTree('audit', changes)).filter(node => node.type === 'details')
  assert.deepEqual(auditDetails.map(node => nodes(node).find(child => child.type === 'summary')?.children[0]),
    ['审计坐标', '模型审查原文'])
  assert.ok(auditDetails.every(node => node.props?.open === undefined))
})

test('plugin settings atomically edit CLI roles and preserve API entries and stale drafts', async () => {
  let cursor = 0
  const states: unknown[] = []
  const reviewer = { adapter: 'api_agent', provider: 'siliconflow', model: 'api-model',
    connection_ref: 'reference', max_requests: 3, max_tool_calls: 3, max_output_tokens: 512 }
  const roleConfig = { schema_version: 2, roles: {
    worker: { adapter: 'codebuddy', model: 'before' }, reviewer,
    inspector: { adapter: 'codex', model: null },
  } }
  let section: { ns: string; revision: number; value: object } = {
    ns: 'dsh-runtime-standalone', revision: 4, value: { roleConfig },
  }
  let accept = false
  const location = { protocol: '' }
  const writes: Array<{ ops: unknown; revision: number }> = []
  const views = loadViews({
    createElement,
    useSyncExternalStore: (_subscribe: unknown, getSnapshot: () => unknown) => getSnapshot(),
    useState(initial: unknown) {
      const i = cursor++
      if (!(i in states)) states[i] = initial
      return [states[i], (next: unknown) => {
        states[i] = typeof next === 'function' ? next(states[i]) : next
      }]
    },
  }, {
    get: () => ({ mutate: async (ops: unknown, revision: number) => {
      writes.push({ ops: structuredClone(ops), revision })
      return accept
    } }),
    describe: () => ({ subscribe: () => () => {},
      getSnapshot: () => ({ view: { writable: true, namespaces: [section] } }) }),
  }, location)
  const view = views.get('plugins.bundle.config')!
  const component = (view({}) as Element).type as View
  const form = () => { cursor = 0; return nodes(component((view({}) as Element).props!)) }
  const control = (type: string, index = 0) => form().filter(node => node.type === type)[index].props!
  const edit = (type: string, value: string) =>
    (control(type).onChange as (event: { target: { value: string } }) => void)({ target: { value } })
  const save = () => (control('button').onClick as () => Promise<void>)()

  assert.equal(form().filter(node => node.type === 'input').length, 2)
  edit('select', 'codex')
  assert.equal(control('input').value, '')
  edit('input', 'bad model')
  assert.equal(control('button').disabled, true)
  await save()
  assert.equal(writes.length, 0)
  edit('input', 'new-model')
  await save()
  assert.deepEqual(writes[0], { revision: 4, ops: [
    { op: 'set', path: ['roleConfig', 'roles', 'worker', 'adapter'], value: 'codex' },
    { op: 'set', path: ['roleConfig', 'roles', 'worker', 'model'], value: 'new-model' },
  ] })
  assert.equal(control('input').value, 'new-model')
  assert.equal(roleConfig.roles.reviewer, reviewer)
  section = { ...section, revision: 5 }
  assert.equal(control('button').disabled, true)
  await save()
  assert.equal(writes.length, 1)

  states.length = 0
  section = { ...section, value: {} }
  accept = true
  edit('input', 'first-model')
  await save()
  assert.deepEqual(writes[1], { revision: 5, ops: [{ op: 'set', path: ['roleConfig'], value: {
    schema_version: 1, roles: {
      worker: { adapter: 'codebuddy', model: 'first-model' },
      reviewer: { adapter: 'codex', model: null },
      inspector: { adapter: 'codex', model: null },
    },
  } }] })

  states.length = 0
  location.protocol = 'dsh-app:'
  section = { ...section, value: { roleConfig } }
  const editApi = (value: string) => (control('input', 1).onChange as
    (event: { target: { value: string } }) => void)({ target: { value } })
  assert.equal(control('input', 1).value, 'api-model')
  editApi('')
  await save()
  assert.equal(writes.length, 2)
  editApi('provider/new-model')
  await save()
  assert.deepEqual(writes[2], { revision: 5, ops: [
    { op: 'set', path: ['roleConfig', 'roles', 'reviewer', 'model'], value: 'provider/new-model' },
  ] })
  assert.equal(roleConfig.roles.reviewer, reviewer)
})
