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

function loadViews(react: unknown, configForms?: unknown, windowLocation: object = {}, navigator?: object,
  environment: object = {}): Map<string, View> {
  const views = new Map<string, View>()
  let plugin: { apply: (ctx: unknown) => void } | undefined
  runInNewContext(source, {
    window: { location: windowLocation, __ModuleLoader__: { load: (registration: { factory: (require: (id: string) => unknown) => unknown }) => {
      plugin = registration.factory(id => id === 'react' ? { useRef: () => ({ current: null }), ...(react as object) }
        : { createPortal: (node: unknown) => node }) as typeof plugin
    } } },
    document: { body: {} }, navigator, Date, AbortController, AbortSignal, URLSearchParams,
    setInterval, clearInterval, setTimeout, clearTimeout, ...environment,
  })
  const slots = { inject: (_: string, callback: () => unknown) => callback(),
    register: (options: { name: string }, component: View) => {
      views.set(options.name, options.name === 'tool.call.toolview' ? props => {
        const element = component(props) as Element
        return (element.type as View)(element.props!)
      } : component)
    } }
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

const textOf = (tree: unknown) => nodes(tree)
  .filter(node => node.type !== 'style')
  .flatMap(node => node.children.filter(child => typeof child === 'string')).join('\n')

async function checkRunningCard(stopReason: string, terminalLabel: string): Promise<void> {
  const now = Date.now()
  const props = { ...startedProps, block: { ...startedProps.block, time: now - 20_000 } }
  const activity = { adapter: 'codex', kind: 'tool', tool: 'commandExecution', status: 'completed', atMs: now - 4_000 }
  const running = (role: string, atMs: number, event = activity) => Response.json({
    state: { phase: 'running' }, progress: { phase: { role, adapter: 'codex', atMs }, activity: event },
  }, { status: 202 })
  const responses = [
    running('worker', now - 10_000),
    running('reviewer', now - 3_000), // Same adapter, but the activity predates the new phase.
    new Response(null, { status: 503 }),
    running('reviewer', now - 3_000, { ...activity, atMs: now - 2_000 }),
    Response.json({ state: { phase: 'settled', stopReason, manifestAvailable: false } }),
  ]
  const values: unknown[] = []
  const refs: { current: unknown }[] = []
  let index = 0
  let refIndex = 0
  let effect: (() => () => void) | undefined
  let timer: (() => void) | undefined
  let calls = 0
  const doc = { activeElement: null as unknown }
  const summary = { focus: () => { doc.activeElement = summary } }
  const view = loadViews({
    createElement,
    useState(initial: unknown) {
      const slot = index++
      if (slot >= values.length) values.push(initial)
      return [values[slot], (update: unknown) => { values[slot] = typeof update === 'function' ? update(values[slot]) : update }]
    },
    useRef(initial: unknown) {
      const slot = refIndex++
      return refs[slot] ??= { current: initial }
    },
    useEffect(fn: () => () => void) { effect ??= fn },
  }, undefined, {}, undefined, {
    document: doc,
    fetch: async (path: string, options: RequestInit) => {
      assert.equal(path, 'api/dsh-runtime.evidence?sessionId=session&childId=00000000-0000-4000-8000-000000000001')
      assert.equal(options.method, undefined)
      assert.ok(options.signal && !options.signal.aborted)
      calls++
      return responses.shift()
    },
    setTimeout: (callback: () => void) => { assert.equal(timer, undefined); timer = callback },
    clearTimeout: () => { timer = undefined },
  }).get('tool.call.toolview')!
  const draw = () => { index = 0; refIndex = 0; return view(props) }
  const flush = () => new Promise<void>(resolve => setImmediate(resolve))
  const tick = async () => { const next = timer; timer = undefined; assert.ok(next); next(); await flush() }
  draw()
  const cleanup = effect!()
  await flush()
  let tree = draw()
  assert.match(textOf(tree), /执行阶段[\s\S]*Worker · Codex[\s\S]*调用已用时[\s\S]*20 秒/u)
  assert.equal(nodes(tree).find(node => node.props?.role === 'status')?.children.join(''), '运行中')
  assert.equal(textOf(tree).match(/命令执行 · 已完成/gu)?.length, 1)
  const details = nodes(tree).find(node => node.type === 'details')
  assert.equal(details?.props?.open, undefined)
  assert.match(textOf(details), /查看最近活动[\s\S]*活动观测时间[\s\S]*状态最后成功读取时间/u)
  assert.equal(calls, 1)

  await tick()
  assert.match(textOf(draw()), /原始复核阶段[\s\S]*暂无可显示的新活动/u)
  assert.doesNotMatch(textOf(draw()), /命令执行/u)
  await tick()
  tree = draw()
  assert.match(textOf(tree), /读取状态失败[\s\S]*上次记录 · 原始复核阶段[\s\S]*重连只能补回活动窗口内仍保留的记录/u)
  assert.doesNotMatch(textOf(tree), /运行失败/u)
  const retry = nodes(tree).find(node => node.children.includes('重新读取'))
  assert.ok(retry)
  const activityRef = nodes(tree).find(node => node.type === 'details')?.props?.ref as { current: unknown }
  activityRef.current = { querySelector: () => summary, contains: (node: unknown) => node === retry }
  doc.activeElement = retry
  ;(retry.props?.onClick as () => void)()
  await flush()
  assert.match(textOf(draw()), /运行中[\s\S]*命令执行 · 已完成/u)
  assert.equal(doc.activeElement, summary)
  assert.doesNotMatch(textOf(draw()), /上次记录|读取状态失败/u)
  const lateTick = timer
  await tick()
  assert.match(textOf(draw()), new RegExp(terminalLabel + '[\\s\\S]*终态清单缺失[\\s\\S]*查看证据状态', 'u'))
  assert.match(textOf(draw()), /查看最近活动/u)
  assert.doesNotMatch(textOf(draw()), /命令执行/u)
  assert.equal(timer, undefined)
  lateTick?.()
  await flush()
  assert.equal(calls, 5)
  cleanup()
}

for (const [reason, label] of [['completed', '已结束'], ['aborted', '已取消'], ['error', '运行失败']]) {
  test(`running card labels stale observations and stops read-only polling on ${reason}`, () => checkRunningCard(reason, label))
}

test('the focused activity keeps its place until the first evidence click after settlement', async () => {
  const terminal = { manifest: {
    status: 'completed', duration_ms: 1000, task_kind: 'repository_inspection',
    workspace_changes: { added_files: [], modified_files: [], deleted_files: [] },
    execution_trajectory: { status: 'not_applicable', turns_used: null },
    audit: { status: 'settled' }, verification: { verdict: 'UNAVAILABLE' },
  }, diff: '' }
  const responses = [Response.json({ state: { phase: 'running' } }, { status: 202 }), Response.json(terminal)]
  const values: unknown[] = []
  const refs: { current: unknown }[] = []
  let index = 0
  let refIndex = 0
  let effect: (() => () => void) | undefined
  let timer: (() => void) | undefined
  const summary = {}
  const trigger = {}
  const detail = { querySelector: () => summary, contains: (node: unknown) => node === summary }
  const document = { body: {}, activeElement: summary }
  const view = loadViews({
    createElement,
    useState(initial: unknown) {
      const slot = index++
      if (slot >= values.length) values.push(initial)
      return [values[slot], (update: unknown) => { values[slot] = typeof update === 'function' ? update(values[slot]) : update }]
    },
    useRef(initial: unknown) {
      const slot = refIndex++
      return refs[slot] ??= { current: initial }
    },
    useEffect(fn: () => () => void) { effect ??= fn },
  }, undefined, {}, undefined, {
    document,
    fetch: async () => responses.shift(),
    setTimeout: (callback: () => void) => { timer = callback },
    clearTimeout: () => { timer = undefined },
  }).get('tool.call.toolview')!
  const draw = () => { index = 0; refIndex = 0; return nodes(view(startedProps)) }
  const flush = () => new Promise<void>(resolve => setImmediate(resolve))
  const activityIn = (tree: Element[]) => tree.find(node => node.type === 'details' && node.props?.key === 'activity')
  const eventHandler = <T>(node: Element, name: string) => node.props?.[name] as (event: T) => void
  draw()
  const cleanup = effect!()
  try {
    await flush()
    const activity = activityIn(draw())!
    ;(activity.props?.ref as { current: unknown }).current = detail
    eventHandler<void>(activity, 'onFocus')(undefined)
    timer!()
    await flush()
    const terminalCard = draw()
    const evidence = terminalCard.find(node => node.type === 'button' && node.children.includes('查看证据'))!
    const terminalActivity = activityIn(terminalCard)!
    ;(evidence.props?.ref as { current: unknown }).current = trigger
    assert.match(textOf(terminalActivity), /活动观察已结束/u)
    eventHandler<{ relatedTarget: object; currentTarget: object }>(terminalActivity, 'onBlur')({
      relatedTarget: trigger, currentTarget: detail,
    })
    assert.ok(activityIn(draw()), 'Pointer focus on the evidence button must not remove the disclosure')
    eventHandler<{ relatedTarget: object }>(evidence, 'onBlur')({ relatedTarget: summary })
    assert.ok(activityIn(draw()), 'Moving focus back to the disclosure keeps it mounted')
    eventHandler<void>(evidence, 'onClick')(undefined)
    const opened = draw()
    assert.ok(opened.some(node => node.type === 'dialog'))
    assert.ok(activityIn(opened), 'B keeps the terminal history entrance mounted')
  } finally {
    cleanup()
  }
})

test('an old response body cannot repopulate activity after the Run card is replaced', async () => {
  let effect: (() => () => void) | undefined
  let finishBody: (value: unknown) => void = () => { throw new Error('Body read did not start') }
  let signal: AbortSignal | null | undefined
  const view = loadViews({
    createElement,
    useState: (initial: unknown) => [initial, () => assert.fail('Old card must not update')],
    useEffect(fn: () => () => void) { effect ??= fn },
  }, undefined, {}, undefined, {
    fetch: async (_: string, options: RequestInit) => {
      signal = options.signal
      return { ok: true, status: 202, json: () => new Promise(resolve => { finishBody = resolve }) }
    },
    setTimeout: () => assert.fail('Old card must not start another poll'),
  }).get('tool.call.toolview')!
  view(startedProps)
  const cleanup = effect!()
  const flush = () => new Promise<void>(resolve => setImmediate(resolve))
  await flush()
  assert.equal(signal?.aborted, false)
  cleanup()
  assert.equal(signal?.aborted, true)
  finishBody({ state: { phase: 'running' }, progress: {} })
  await flush()
})

test('invalid or absent run coordinates leave the activity disclosure out', () => {
  const view = loadViews({
    createElement, useState: (initial: unknown) => [initial, () => {}], useEffect: () => {},
  }).get('tool.call.toolview')!
  for (const props of [{ ...startedProps, phase: 'call' }, { ...startedProps, sessionId: '' },
    { ...startedProps, block: { content: [{ type: 'text', text: 'not a run' }] } }]) {
    assert.doesNotMatch(textOf(view(props)), /查看最近活动/u)
  }
})

type MissingEvidence = 'aborted' | 'error' | 'ended'
function renderTree(tab: string, changes: Record<string, unknown>, scope?: Record<string, unknown>,
  relocation?: { status: 'verified_copy'; createdAt: string }, modelObservations?: unknown,
  terminal?: Record<string, unknown> | MissingEvidence, diff = 'patch text', navigator?: object,
  supplemental?: unknown): Element {
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
          }, diff, relocation }, true, tab, Date.now(), null, false, supplemental,
        ]
        return [values[index++] ?? initial, () => {}]
      }
    })(),
    useEffect: () => {},
  }
  const view = loadViews(react, undefined, {}, navigator).get('tool.call.toolview')!
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

test('drawer distinguishes the read-only inspector from a mandatory reviewer', () => {
  const model = { role: 'inspector', adapter: 'codex', invocation_index: 1,
    requested_model: null, reported_model: 'inspection-model' }
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const draw = (entry: unknown) => render('trajectory', changes, undefined, undefined,
    { version: 1, source: 'codex_thread_start', entries: [entry] },
    { task_kind: 'repository_inspection', verification: { verdict: 'UNAVAILABLE' } })
  assert.match(draw(model), /只读检查模型：Codex · 请求 CLI 默认 · CLI 启动返回 inspection-model/u)
  assert.match(draw(model), /模型审查判决：不适用/u)
  assert.match(draw({ ...model, role: 'reviewer' }), /只读检查模型：未记录/u)
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
  for (const state of ['aborted', 'error', 'ended'] as const) {
    assert.match(draw(state), /无法确认文件是否发生变动/u)
    assert.match(draw(state), /查看证据状态/u)
    assert.doesNotMatch(draw(state), /BLOCKED/u)
  }
  assert.doesNotMatch(draw({ task_kind: 'repository_inspection', verification: { verdict: 'UNAVAILABLE' } }), /现有证据无法/u)
})

test('overview separates task, original review, unread supplemental review and evidence gaps', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const overview = (terminal: Record<string, unknown>) => nodes(renderTree('trajectory', changes,
    undefined, undefined, undefined, terminal)).filter(node => node.type === 'dt' || node.type === 'dd')
    .map(node => textOf(node))
  const failed = overview({ status: 'timed_out', verification: { verdict: 'UNAVAILABLE' },
    execution_trajectory: { status: 'incomplete' }, audit: { status: 'unavailable' } }).join('\n')
  assert.match(failed, /任务结果[\s\S]*运行超时[\s\S]*原始审查[\s\S]*无法确认[\s\S]*追加复核[\s\S]*不适用[\s\S]*证据缺口/u)
  assert.match(failed, /执行过程统计不完整或不可用[\s\S]*调用审计未确认结算/u)
  assert.match(overview({}).join('\n'), /追加复核[\s\S]*尚未读取/u)
  assert.match(overview({ task_kind: 'repository_inspection', verification: { verdict: 'UNAVAILABLE' } }).join('\n'),
    /原始审查[\s\S]*不适用/u)
})

test('review wording separates proven non-dispatch, invoked failures and old unknown records', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const execution = (status: string, reason: string) => ({ version: 1, source: 'runtime_invocation_evidence', status, reason })
  const draw = (terminal: Record<string, unknown>) => render('audit', changes, undefined, undefined, undefined, terminal)
  const failed = { status: 'failed', verification: { verdict: 'UNAVAILABLE', invocation_binding: 'invalid' } }
  const notStarted = { ...failed, review_execution: execution('not_started', 'worker_terminated_before_review') }
  const before = JSON.stringify(notStarted)
  const notStartedText = draw(notStarted)
  assert.match(notStartedText, /原始审查未执行：Worker 阶段终止/u)
  assert.match(notStartedText, /原始判决：未执行（无审查判决）/u)
  assert.match(notStartedText, /审查调用绑定：未建立（没有 Reviewer 调用）/u)
  assert.doesNotMatch(notStartedText, /审查调用证据未通过绑定校验|审查调用绑定：校验失败/u)
  assert.equal(JSON.stringify(notStarted), before, 'Rendering must not rewrite historical evidence')

  const invoked = draw({ ...failed, review_execution: execution('invoked', 'reviewer_invocation_recorded') })
  assert.match(invoked, /原始审查已发起，结果未确认/u)
  assert.match(invoked, /不代表 CLI 已成功启动或审查已完成/u)
  assert.match(invoked, /审查调用绑定：证据不匹配或校验失败/u)
  assert.match(invoked, /原始判决：无法确认/u)

  for (const metadata of [undefined, execution('unknown', 'insufficient_bound_evidence'),
    execution('not_started', 'invalid-reason'), { ...execution('not_started', 'worker_terminated_before_review'), version: 2 }]) {
    const old = draw({ ...failed, review_execution: metadata, model_observations: { entries: [] },
      authority_phases: { phase_2_codex_effective_write: null }, execution_trajectory: { status: 'unavailable' } })
    assert.match(old, /执行情况未记录，无法区分未执行与绑定不匹配/u)
    assert.match(old, /审查调用绑定：校验未通过；无法区分未执行与绑定不匹配/u)
    assert.doesNotMatch(old, /原始审查未执行：|没有 Reviewer 调用/u)
  }
  for (const override of [
    { audit: { status: 'unavailable' } }, { status: 'completed' },
    { verification: { verdict: 'PASS', invocation_binding: 'matched' } },
  ]) assert.doesNotMatch(draw({ ...notStarted, ...override }), /没有 Reviewer 调用/u)
  for (const verdict of ['PASS', 'FAIL']) {
    const text = draw({ status: verdict === 'PASS' ? 'completed' : 'failed',
      verification: { verdict, invocation_binding: 'matched' },
      review_execution: execution('invoked', 'reviewer_invocation_recorded') })
    assert.ok(text.includes('原始判决：' + verdict))
    assert.match(text, /审查调用绑定：已匹配/u)
  }
})

test('long patches and audit details are collapsed by default', () => {
  const changes = {
    source: 'workspace_pre_post_snapshot_delta', baseline_compared: true,
    observation_boundary: 'window_observed_changes',
    added_files: ['new.txt'], modified_files: [], deleted_files: [],
  }
  const text = 'x'.repeat(200001)
  const patch = nodes(renderTree('changes', changes, undefined, undefined, undefined, undefined, text))
    .find(node => node.type === 'details' && nodes(node).some(child => child.children.includes('查看补丁')))!
  assert.equal(patch.props?.open, undefined)
  assert.equal(nodes(patch).find(node => node.type === 'pre')?.children[0], text.slice(0, 200000))
  assert.match(nodes(patch).find(node => node.type === 'p')?.children.join('') ?? '', /仅展示/u)
  const auditDetails = nodes(renderTree('audit', changes)).filter(node => node.type === 'details' && node.props?.key !== 'activity')
  assert.deepEqual(auditDetails.map(node => nodes(node).find(child => child.type === 'summary')?.children[0]),
    ['查看 Worker 公开消息预览', '模型审查原文', '技术证据与坐标'])
  assert.ok(auditDetails.every(node => node.props?.open === undefined))
})

test('summary preview and clipboard match without leaking file, model, output or path values', async () => {
  const marker = {
    version: 1, source: 'post_run_worktree_observation', scope: 'dsh_controlled_snapshot_v1',
    file_count: 2, base_commit: 'b'.repeat(40), content_sha256: 'c'.repeat(64),
  }
  const changes = {
    source: 'workspace_pre_post_snapshot_delta', baseline_compared: true,
    observation_boundary: 'window_observed_changes', patch_complete: false,
    added_files: ['private/source.txt'], modified_files: [], deleted_files: [],
    diff_content_ref: '/private/diff.patch',
  }
  const models = { version: 1, source: 'codex_thread_start', entries: [
    { role: 'worker', adapter: 'codex', invocation_index: 1, requested_model: 'sk-private', reported_model: 'gpt-private' },
  ] }
  let copied = ''
  const tree = renderTree('audit', changes, undefined, undefined, models, {
    status: 'failed', target_observation: marker,
    verification: { verdict: 'FAIL', evidence_text: 'private review output' },
  }, 'private diff content', { clipboard: { writeText: async (text: string) => { copied = text } } })
  const view = nodes(tree).find(node => typeof node.type === 'function' && typeof node.props?.summary === 'string')!
  const panel = nodes((view.type as View)(view.props!))
  const preview = panel.find(node => node.type === 'textarea')!
  const copy = panel.find(node => node.type === 'button')!
  assert.equal(preview.props?.readOnly, true)
  await (copy.props?.onClick as () => Promise<void>)()
  assert.equal(copied, preview.props?.value)
  assert.match(copied, /内容摘要 SHA-256：c{64}/u)
  assert.match(copied, /模型审查判决：FAIL/u)
  assert.match(copied, /实际受审快照：未绑定/u)
  assert.match(copied, /补丁完整性：不完整/u)
  assert.match(copied, /执行阶段模型来源：Codex · CLI 启动返回 · 已记录/u)
  assert.doesNotMatch(copied, /private/u)
  for (const [observation, label] of [
    [undefined, '运行后工作树观察：未记录'],
    [{ ...marker, content_sha256: null }, '运行后工作树观察：覆盖不完整'],
  ] as const) {
    const history = nodes(renderTree('audit', changes, undefined, undefined, undefined, { target_observation: observation }))
    const summary = history.find(node => typeof node.props?.summary === 'string')?.props?.summary
    assert.ok(typeof summary === 'string' && summary.includes(label))
    assert.doesNotMatch(summary, /内容摘要 SHA-256/u)
  }
})

test('supplemental INCONCLUSIVE stays separate from original PASS and current-target freshness', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  for (const [freshness, message] of [['matched', '本次核对一致'], ['stale', '历史结果 · 当前目标已变化'], ['unknown', '历史结果 · 当前目标尚未核实']]) {
    const tree = renderTree('audit', changes, undefined, undefined, undefined, undefined, '', undefined,
      { result: { status: 'ready' }, review: { status: 'completed', verdict: 'INCONCLUSIVE', freshness } })
    const overview = nodes(tree).find(node => node.type === 'dl')!
    assert.match(textOf(overview), /原始审查[\s\S]*PASS[\s\S]*追加复核[\s\S]*INCONCLUSIVE/u)
    assert.ok(textOf(overview).includes(message))
    assert.match(textOf(overview), /仅审已保存的文本补丁，不替代原始判决/u)
  }
})

test('unread, no saved review and failed read are distinct; old manifests never imply zero changes', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const draw = (review: unknown) => textOf(nodes(renderTree('audit', changes, undefined, undefined, undefined,
    undefined, '', undefined, { result: { status: 'ready' }, review })).find(node => node.type === 'dl'))
  assert.match(draw(null), /未发现追加记录/u)
  assert.match(draw({ status: 'read_failed' }), /读取失败[\s\S]*不能据此判断没有历史结果/u)
  assert.match(draw({ status: 'reading' }), /正在核对/u)
  const old = render('audit', changes)
  assert.match(old, /文件变化无法确认/u)
  assert.match(old, /清单未记录 TaskState 引用（旧记录可能缺少）/u)
  assert.match(old, /实际模型尚未核实/u)
  assert.match(old, /上下文独立性：此清单未单独记录/u)
  assert.doesNotMatch(old, /观察到 0 个文件变化/u)
})

test('supplemental panel stays mounted across tabs and handoff is outside the detail panels', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  for (const tab of ['trajectory', 'changes', 'audit']) {
    const tree = renderTree(tab, changes)
    const audit = nodes(tree).find(node => node.props?.['aria-label'] === '审查与证据详情')!
    assert.equal(audit.props?.hidden, tab !== 'audit')
    assert.ok(nodes(audit).some(node => typeof node.type === 'function' && node.props?.childId))
    assert.ok(!nodes(audit).some(node => node.props?.summary))
    const handoff = nodes(tree).find(node => node.props?.className === 'rt-handoff')!
    assert.ok(nodes(handoff).some(node => node.props?.summary))
    assert.match(textOf(tree), /执行过程[\s\S]*文件变更[\s\S]*审查与证据/u)
  }
})

test('opening supplemental details makes no requests; explicit check only reads and distinguishes network failure', async () => {
  let index = 0
  const values: unknown[] = []
  const observations: unknown[] = []
  const effects: (() => void)[] = []
  const requests: { path: string; method: string }[] = []
  const view = loadViews({ createElement,
    useState(initial: unknown) {
      const slot = index++
      if (slot >= values.length) values.push(initial)
      return [values[slot], (value: unknown) => { values[slot] = value }]
    }, useEffect: (effect: () => void) => { effects.push(effect) },
  }, undefined, {}, undefined, { fetch: async (path: string, init: RequestInit) => {
    requests.push({ path, method: init?.method ?? 'GET' })
    if (path.includes('snapshot-review')) throw new Error('disconnected')
    return Response.json({ status: 'ready', scope: 'saved_text_patch', patch: 'safe' })
  } }).get('tool.call.toolview')!
  // Locate the material component without running the Runtime card's effects or poller.
  index = 0
  values.push({ manifest: { status: 'completed', duration_ms: 1, task_kind: 'repository_change',
    workspace_changes: { added_files: [], modified_files: [], deleted_files: [] },
    execution_trajectory: { status: 'available' }, audit: { status: 'settled' }, verification: { verdict: 'PASS' } }, diff: '' }, true, 'audit', 0, null, false, null)
  const node = nodes(view(startedProps)).find(node => typeof node.type === 'function' && node.props?.onObservation)!
  values.length = 0
  const draw = () => { index = 0; effects.length = 0; return (node.type as View)({ ...node.props, onObservation: (value: unknown) => observations.push(value) }) }
  let panel = draw()
  effects.forEach(effect => effect())
  assert.equal(requests.length, 0)
  const check = nodes(panel).find(item => item.children.includes('核对并预览材料'))!
  await (check.props?.onClick as () => Promise<void>)()
  panel = draw()
  effects.forEach(effect => effect())
  assert.match(textOf(panel), /记录读取失败，历史结果尚未确认/u)
  assert.equal(requests.length, 2)
  assert.ok(requests.every(item => item.method === 'GET'))
  assert.ok(observations.length)
})

test('reopening the drawer clears the supplemental observation without querying or sending', () => {
  const changes = { added_files: [], modified_files: [], deleted_files: [] }
  const observed = { result: { status: 'ready' }, review: { status: 'completed', verdict: 'PASS', freshness: 'matched' } }
  const tree = renderTree('audit', changes, undefined, undefined, undefined, undefined, '', undefined, observed)
  // The trigger deliberately resets the observation; a fresh material panel has not checked the target.
  const writes: { slot: number; value: unknown }[] = []
  let index = 0
  const values = [{ manifest: { status: 'completed', duration_ms: 1, task_kind: 'repository_change',
    workspace_changes: changes, execution_trajectory: { status: 'available' }, audit: { status: 'settled' },
    verification: { verdict: 'PASS' } }, diff: '' }, false, 'audit', Date.now(), null, false, observed]
  const view = loadViews({ createElement, useEffect: () => {}, useState(initial: unknown) {
    const slot = index++
    return [values[slot] ?? initial, (value: unknown) => writes.push({ slot, value })]
  } }).get('tool.call.toolview')!
  const trigger = nodes(view(startedProps)).find(node => node.children.includes('查看证据'))!
  ;(trigger.props?.onClick as () => void)()
  assert.ok(writes.some(write => write.slot === 6 && write.value === null))
  assert.match(textOf(nodes(tree).find(node => node.type === 'dl')), /追加复核[\s\S]*PASS/u)
})

function historyHarness(replies: Array<Response | Error | (() => Promise<unknown>)>, preview = false) {
  const values: unknown[] = [], refs: Array<{ current: unknown }> = []
  let index = 0, refIndex = 0, effect: (() => () => void) | undefined, timer: (() => void) | undefined
  const calls: Array<{ path: string; signal?: AbortSignal | null }> = []
  const view = loadViews({ createElement,
    useState(initial: unknown) {
      const slot = index++
      if (slot >= values.length) values.push(initial)
      return [values[slot], (update: unknown) => { values[slot] = typeof update === 'function' ? update(values[slot]) : update }]
    }, useRef(initial: unknown) { return refs[refIndex++] ??= { current: initial } },
    useEffect(fn: () => () => void) { effect = fn },
  }, undefined, {}, undefined, {
    fetch: async (path: string, options: RequestInit) => {
      assert.equal(options.method, undefined)
      assert.match(path, preview ? /view=public-preview/u : /view=activity/u)
      calls.push({ path, signal: options.signal })
      const reply = replies.shift()
      if (reply instanceof Error) throw reply
      if (typeof reply === 'function') return { ok: true, json: reply }
      assert.ok(reply, 'No unexpected reads or model calls')
      return reply
    }, setTimeout: (callback: () => void) => { assert.equal(timer, undefined); timer = callback },
    clearTimeout: () => { timer = undefined },
  }).get('tool.call.toolview')!
  const root = view(startedProps)
  const child = nodes(root).find(node => typeof node.type === 'function' && node.type.name === (preview ? 'PublicPreview' : 'ActivityHistory'))!
  assert.ok(child)
  values.length = refs.length = 0
  const draw = (enabled = true, ended = false, overrides: object = {}) => {
    index = refIndex = 0
    return (child.type as View)({ ...child.props, enabled, ended, ...overrides })
  }
  const flush = () => new Promise<void>(resolve => setImmediate(resolve))
  const start = () => { draw(); return effect!() }
  const tick = async () => { const callback = timer; timer = undefined; assert.ok(callback); callback(); await flush() }
  return { draw, flush, start, tick, calls, effect: () => effect!(), scheduled: () => !!timer }
}

const historyStream = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
function historyEvent(seq: number, role = 'worker', kind = 'tool') {
  return { v: 1, type: 'event', runId: 'dsh-runtime-00000000-0000-4000-8000-000000000001',
    workspaceId: 'session', streamId: historyStream, seq, role, adapter: 'codex',
    invocationId: role === 'reviewer' ? 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff' : 'cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa',
    invocationIndex: role === 'reviewer' ? 2 : 1, atMs: Date.now(), kind,
    status: kind === 'phase' ? 'dispatched' : 'completed', ...(kind === 'tool' ? { tool: 'commandExecution' } : {}) }
}
function historyReply(events: unknown[], changes = {}) {
  return Response.json({ version: 1, status: 'available', streamId: historyStream,
    runId: 'dsh-runtime-00000000-0000-4000-8000-000000000001', retention: 'host_memory',
    limitEvents: 50, limitBytes: 32768, retainedBytes: 1500, earliestSeq: 1,
    lastSeq: 2, nextCursor: 2, closed: false, sourceClosed: false, established: true,
    truncated: false, gaps: [], reset: false, events, ...changes })
}

test('B history incrementally reads source rows, deduplicates and recovers only the retained window', async () => {
  const initial = [historyEvent(1, 'worker', 'phase'), historyEvent(2)]
  const review = [historyEvent(3, 'reviewer', 'phase'), historyEvent(4, 'reviewer')]
  const recent = [historyEvent(60, 'reviewer'), historyEvent(61, 'reviewer')]
  const h = historyHarness([historyReply(initial), historyReply(review, { lastSeq: 4, nextCursor: 4 }),
    historyReply(review, { lastSeq: 4, nextCursor: 4 }), new Response(null, { status: 503 }),
    historyReply(recent, { earliestSeq: 60, lastSeq: 61, nextCursor: 61, truncated: true, gaps: ['window_truncated'] })])
  const cleanup = h.start()
  try {
    await h.flush()
    assert.equal(nodes(h.draw()).filter(n => n.type === 'li').length, 2)
    await h.tick()
    assert.equal(nodes(h.draw()).filter(n => n.type === 'li').length, 4)
    assert.match(textOf(h.draw()), /#4 · Reviewer · Codex[\s\S]*#3 · Reviewer · Codex[\s\S]*#2 · Worker · Codex/u)
    assert.match(h.calls[1].path, /after=2&stream=/u)
    await h.tick()
    assert.equal(nodes(h.draw()).filter(n => n.type === 'li').length, 4)
    await h.tick()
    assert.match(textOf(h.draw()), /活动读取失败[\s\S]*以下为上次记录/u)
    await h.tick()
    assert.match(textOf(h.draw()), /窗口已截断[\s\S]*记录存在缺口[\s\S]*#61 · Reviewer/u)
    assert.doesNotMatch(textOf(h.draw()), /#2 · Worker|活动读取失败/u)
    assert.match(h.calls.at(-1)!.path, /after=4/u)
  } finally { cleanup() }
})

test('B history distinguishes empty, unestablished, expired and post-restart records', async () => {
  for (const [response, expected] of [
    [historyReply([], { lastSeq: 0, nextCursor: 0 }), '当前窗口暂无已记录的安全活动'],
    [historyReply([], { lastSeq: 0, nextCursor: 0, established: false }), '尚未确认源活动通道'],
    [Response.json({ version: 1, status: 'unavailable', reason: 'expired' }), '活动记录已过期'],
    [Response.json({ version: 1, status: 'unavailable', reason: 'not_recorded_in_this_host' }), '本 Host 无可恢复的活动记录'],
  ] as const) {
    const h = historyHarness([response])
    const cleanup = h.start()
    await h.flush()
    assert.ok(textOf(h.draw()).includes(expected))
    assert.doesNotMatch(textOf(h.draw()), /任务失败|已完成任务/u)
    cleanup()
  }
})

test('B history rejects sensitive fields and ignores response bodies after terminal cleanup', async () => {
  let finish!: (value: unknown) => void
  const h = historyHarness([() => new Promise(resolve => { finish = resolve })])
  const cleanup = h.start()
  await h.flush()
  assert.equal(h.calls[0].signal?.aborted, false)
  cleanup()
  assert.equal(h.calls[0].signal?.aborted, true)
  finish(await historyReply([historyEvent(1)]).json())
  await h.flush()
  assert.doesNotMatch(textOf(h.draw()), /#1/u)
  assert.equal(h.calls.length, 1)
  assert.equal(h.scheduled(), false)
  const bad = historyHarness([historyReply([{ ...historyEvent(1), text: 'SECRET BODY' }])])
  const stop = bad.start()
  await bad.flush()
  assert.match(textOf(bad.draw()), /活动读取失败/u)
  assert.doesNotMatch(textOf(bad.draw()), /SECRET BODY/u)
  stop()
})

test('B expansion is read-only and terminal sealed windows stop polling', async () => {
  const h = historyHarness([historyReply([historyEvent(1)], { lastSeq: 1, nextCursor: 1, closed: true })])
  h.draw(false)
  const disabled = h.effect()
  assert.equal(h.calls.length, 0)
  assert.equal(disabled, undefined)
  h.draw(true, true)
  const cleanup = h.effect()!
  await h.flush()
  assert.equal(h.calls.length, 1)
  assert.equal(h.scheduled(), false)
  assert.match(textOf(h.draw()), /活动窗口已封存/u)
  cleanup()
})

test('B terminal final read cancels an earlier response and keeps the sealed window frozen', async () => {
  let finish!: (value: unknown) => void
  const h = historyHarness([() => new Promise(resolve => { finish = resolve }),
    historyReply([historyEvent(1)], { lastSeq: 1, nextCursor: 1, closed: true })])
  const old = h.start()
  await h.flush()
  old()
  h.draw(true, true)
  const stop = h.effect()!
  await h.flush()
  assert.match(textOf(h.draw()), /活动窗口已封存/u)
  finish(await historyReply([historyEvent(999)], { lastSeq: 999, nextCursor: 999 }).json())
  await h.flush()
  assert.doesNotMatch(textOf(h.draw()), /#999/u)
  assert.match(textOf(h.draw()), /#1 · Worker/u)
  assert.equal(h.calls.length, 2)
  assert.equal(h.scheduled(), false)
  stop()
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

function previewReply(text = '<script>alert(1)</script> **literal** https://example.test', changes = {}) {
  const runId = 'dsh-runtime-00000000-0000-4000-8000-000000000001'
  const data = { version: 1, status: 'available', runId, workspaceId: 'session', streamId: historyStream,
    retention: 'host_memory', limitMessages: 8, limitBytes: 16384, limitTextBytes: 1024,
    retainedBytes: 600, lastSeq: 1, closed: false, sourceClosed: false, established: true, truncated: false, issues: [],
    messages: [{ v: 1, type: 'message', runId, workspaceId: 'session', streamId: historyStream,
      seq: 1, invocationId: historyStream, invocationIndex: 1, role: 'worker', adapter: 'codex',
      itemId: 'message-1', phase: 'commentary', atMs: Date.now(), text, truncated: false }], ...changes }
  data.retainedBytes = data.messages.reduce((bytes, message) => bytes + Buffer.byteLength(JSON.stringify(message)), 0)
  return Response.json(data)
}

test('C1 is collapsed by default and renders commentary as literal plaintext only', async () => {
  const h = historyHarness([previewReply()], true)
  assert.equal(h.draw(false), null)
  assert.equal(h.effect(), undefined)
  assert.equal(h.calls.length, 0)
  const stop = h.start()
  await h.flush()
  const tree = h.draw()
  assert.match(textOf(tree), /不保证脱敏/u)
  assert.equal(nodes(tree).find(n => n.type === 'pre')!.children[0], '<script>alert(1)</script> **literal** https://example.test')
  assert.equal(nodes(tree).some(n => n.type === 'a' || n.type === 'script' || n.props?.dangerouslySetInnerHTML), false)
  stop()
  assert.equal(h.scheduled(), false)
})

test('C1 rejects cross-run, cross-session and oversize body responses', async () => {
  for (const response of [previewReply('body', { runId: 'another-run' }),
    previewReply('body', { workspaceId: 'another-session' }), previewReply('漢'.repeat(342)),
    previewReply('body', { messages: Array(9).fill({ text: 'body' }) })]) {
    const h = historyHarness([response], true)
    const stop = h.start()
    await h.flush()
    assert.match(textOf(h.draw()), /预览读取失败/u)
    assert.equal(nodes(h.draw()).some(n => n.type === 'pre'), false)
    stop()
  }
})

test('C1 hides prior identity immediately and ignores late response after close', async () => {
  let finish!: (value: unknown) => void
  const h = historyHarness([previewReply('first'), () => new Promise(resolve => { finish = resolve })], true)
  const stop = h.start()
  await h.flush()
  assert.match(textOf(h.draw()), /first/u)
  assert.doesNotMatch(textOf(h.draw(true, false, { sessionId: 'other' })), /first/u)
  await h.tick()
  stop()
  finish(await previewReply('late').json())
  await h.flush()
  assert.doesNotMatch(textOf(h.draw()), /late/u)
  assert.equal(h.scheduled(), false)
})

test('C1 distinguishes truncation, unknown empty and legacy unavailable', async () => {
  for (const [reply, expected] of [
    [previewReply('part', { truncated: true, issues: ['source_gap'], closed: true }), /窗口已截断[\s\S]*缺口/u],
    [previewReply('', { messages: [], lastSeq: 0, established: false, closed: true }), /尚未确认[\s\S]*不能据此判断任务未执行/u],
    [Response.json({ version: 1, status: 'unavailable', reason: 'not_recorded_in_this_host' }), /旧版、重启/u],
  ] as const) {
    const h = historyHarness([reply], true)
    const stop = h.start()
    await h.flush()
    assert.match(textOf(h.draw()), expected)
    assert.equal(h.scheduled(), false)
    stop()
  }
})


test('C1 strictly rejects unknown fields, invalid message identity, timestamps and retained-byte claims', async () => {
  const base = await previewReply().json()
  const cases = [
    { ...base, unexpected: 'field' },
    { version: 1, status: 'unavailable', reason: 'expired', text: 'unexpected' },
    { ...base, retainedBytes: base.retainedBytes - 1 },
    { ...base, issues: ['unknown_issue'] },
    { ...base, lastSeq: 8, retainedBytes: 16384, messages: Array.from({ length: 8 }, (_, i) => ({
      ...base.messages[0], seq: i + 1, itemId: `item-${i}`, text: '\u0000'.repeat(1024),
    })) },
    ...[{ invocationId: 'not-a-uuid' }, { itemId: '../unsafe' }, { itemId: 'a'.repeat(129) },
      { atMs: 0 }, { atMs: 1.5 }, { unexpected: 'body' }].map(change => ({ ...base, messages: [{ ...base.messages[0], ...change }] })),
  ]
  for (const data of cases) {
    const h = historyHarness([Response.json(data)], true)
    const stop = h.start()
    await h.flush()
    assert.match(textOf(h.draw()), /预览读取失败/u)
    assert.equal(nodes(h.draw()).some(n => n.type === 'pre'), false)
    stop()
  }
})
