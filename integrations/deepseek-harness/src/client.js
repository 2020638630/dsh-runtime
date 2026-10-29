/** Browser half of the standalone Runtime plugin. Uses only the official module table. */
window.__ModuleLoader__.load({
  id: '@dsh-runtime/harness-plugin',
  factory(require) {
    const React = require('react')
    const { createPortal } = require('react-dom')
    const h = React.createElement
    const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/
    const labels = { trajectory: '执行轨迹', changes: '实际变动', audit: '审计' }

    function startedChild(props) {
      if (props.phase !== 'result') return null
      const text = (props.block?.content ?? []).filter(item => item.type === 'text')
        .map(item => item.text).join('\n').trim()
      const match = /^(?:started subagent |started governed DSH Runtime task )([0-9a-f-]+)$/.exec(text)
      return match && UUID.test(match[1]) ? match[1] : null
    }

    function validEvidence(value) {
      const manifest = value?.manifest
      const changes = manifest?.workspace_changes
      const trajectory = manifest?.execution_trajectory
      const audit = manifest?.audit
      const verification = manifest?.verification
      return typeof manifest?.status === 'string'
        && Number.isFinite(manifest.duration_ms) && manifest.duration_ms >= 0
        && Array.isArray(changes?.added_files) && changes.added_files.every(file => typeof file === 'string')
        && Array.isArray(changes?.modified_files) && changes.modified_files.every(file => typeof file === 'string')
        && Array.isArray(changes?.deleted_files) && changes.deleted_files.every(file => typeof file === 'string')
        && typeof trajectory?.status === 'string'
        && (trajectory.turns_used === null || Number.isSafeInteger(trajectory.turns_used))
        && typeof audit?.status === 'string'
        && typeof verification?.verdict === 'string'
        && typeof value.diff === 'string'
        && (value.relocation === undefined || (value.relocation?.status === 'verified_copy'
          && typeof value.relocation?.createdAt === 'string'))
    }

    const panel = { padding: '16px 20px', overflow: 'auto', overflowWrap: 'anywhere' }
    const button = { border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', padding: '6px 9px' }
    const pre = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12 }
    const line = (label, value) => h('p', { key: label }, `${label}：${value ?? '未知'}`)

    function EvidenceRow(props) {
      const id = startedChild(props)
      const [state, setState] = React.useState('waiting')
      const [open, setOpen] = React.useState(false)
      const [tab, setTab] = React.useState('trajectory')
      const [now, setNow] = React.useState(Date.now())
      const start = props.phase === 'result' ? props.block.callTime ?? props.block.time : props.block.time

      React.useEffect(() => {
        if (!id) return
        const lifetime = new AbortController()
        let pending = false
        let done = false
        let missing = 0
        async function load() {
          if (pending || done || lifetime.signal.aborted) return
          pending = true
          try {
            const query = new URLSearchParams({ sessionId: props.sessionId, childId: id })
            const response = await fetch(`api/dsh-runtime.evidence?${query}`, { signal: lifetime.signal })
            if (response.status === 404) {
              if (++missing >= 10) { done = true; setState('unavailable') }
              return
            }
            if (!response.ok && response.status !== 202) {
              done = true
              setState('unavailable')
              return
            }
            const value = await response.json()
            if (validEvidence(value)) {
              done = true
              setState(value)
            } else if (value?.state?.phase === 'settled') {
              done = true
              setState(value.state.stopReason === 'aborted' ? 'aborted'
                : value.state.stopReason === 'error' ? 'error' : 'unavailable')
            } else if (response.status === 200 || value?.state?.phase !== 'running') {
              done = true
              setState('unavailable')
            }
          } catch {
            if (!lifetime.signal.aborted) { done = true; setState('unavailable') }
          } finally { pending = false }
        }
        void load()
        const timer = setInterval(() => { void load() }, 3000)
        return () => { lifetime.abort(); clearInterval(timer) }
      }, [id, props.sessionId])

      React.useEffect(() => {
        if (state !== 'waiting') return
        const timer = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(timer)
      }, [state])
      React.useEffect(() => {
        if (!open) return
        const close = event => { if (event.key === 'Escape') setOpen(false) }
        window.addEventListener('keydown', close)
        return () => window.removeEventListener('keydown', close)
      }, [open])

      const ready = typeof state === 'object' ? state : null
      const manifest = ready?.manifest
      const changes = manifest?.workspace_changes
      const count = changes ? changes.added_files.length + changes.modified_files.length + changes.deleted_files.length : 0
      const observed = changes?.source === 'workspace_pre_post_snapshot_delta'
        && changes?.baseline_compared === true
        && changes?.observation_boundary === 'window_observed_changes'
      const scope = manifest?.evidence_scope
      const attributionKnown = scope?.change_attribution === 'not_established_shared_workspace'
      const summary = ready ? `${manifest.status} · ${Math.round(manifest.duration_ms / 1000)} 秒${ready.relocation ? ' · 历史证据副本' : ''}`
        : state === 'waiting' ? (id ? `等待证据 ${Math.max(0, Math.round((now - start) / 1000))} 秒` : '正在启动')
          : state === 'aborted' ? '已取消'
            : state === 'error' ? '运行失败' : '终态证据不可用'
      let body = null
      if (ready && tab === 'trajectory') {
        const trajectory = manifest.execution_trajectory
        body = [line('轨迹状态', trajectory.status), line('轮次', trajectory.turns_used ?? '未记录'),
          h('ul', { key: 'tools' }, Object.entries(trajectory.tool_operations_summary ?? {})
            .map(([name, count]) => h('li', { key: name }, `${name}：${count}`)))]
      } else if (ready && tab === 'changes') {
        body = [line('文件范围证据', observed ? '运行前后快照观察' : '不可用：未确认可比的前后快照'),
          line('快照覆盖', observed ? 'Git 已跟踪文件及非忽略的未跟踪文件；受排除策略约束，补丁另有大小上限' : '未知'),
          observed ? line('排除路径', Array.isArray(changes.scope_exclusions)
            ? changes.scope_exclusions.join('、') || '无' : '未记录') : null,
          line('变动归属', observed && attributionKnown ? '未证明；工作区未物理隔离，可能有并发编辑' : '未知'),
          observed ? line('观察到的变化', count === 0 ? '无' : `${count} 项`) : null,
          observed ? line('新增', changes.added_files.join('、') || '无') : null,
          observed ? line('修改', changes.modified_files.join('、') || '无') : null,
          observed ? line('删除', changes.deleted_files.join('、') || '无') : null,
          observed && count ? line('补丁', changes.patch_applicable ? '可应用' : '仅供查看') : null,
          observed && ready.diff ? h('pre', { key: 'diff', style: pre }, ready.diff.slice(0, 200000)) : null]
      } else if (ready) {
        const review = manifest.review_trajectory
        body = [line('审计状态', manifest.audit.status), line('调用 ID', manifest.audit.call_id),
          line('输出摘要', manifest.audit.stdout_sha256), line('模型审查判决', manifest.verification.verdict),
          line('判决范围', '模型报告；文件变化由独立快照观察，不能据此认定变动归属'),
          review?.source === 'api_agent_safe_event_trace'
            ? line('API 审查轨迹', review.status) : null,
          review?.source === 'api_agent_safe_event_trace' && review.terminal_reason
            ? line('API 审查终态', review.terminal_reason) : null,
          review?.source === 'api_agent_safe_event_trace' && review.failure_code
            ? line('API 审查失败类别', review.failure_code) : null,
          review?.source === 'api_agent_safe_event_trace' && review.status === 'available'
            ? h('ul', { key: 'review-tools' }, Object.entries(review.tool_operations_summary ?? {})
              .map(([name, count]) => h('li', { key: name }, `${name}：${count}`))) : null,
          line('模型审查原文', ''),
          h('pre', { key: 'basis', style: pre }, manifest.verification.evidence_text ?? '未知')]
      }
      return h('div', { 'data-tool': 'dsh_runtime', style: { minWidth: 0 } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, minHeight: 30 } },
          h('strong', null, 'DSH Runtime'),
          h('span', { style: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, summary),
          ready && h('button', { type: 'button', style: button, onClick: () => setOpen(true) }, '查看证据')),
        open && ready && createPortal(h('div', {
          style: { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgb(0 0 0 / 42%)', display: 'flex', justifyContent: 'flex-end' },
          onMouseDown: event => { if (event.target === event.currentTarget) setOpen(false) },
        }, h('section', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'DSH Runtime',
          style: { width: 'min(560px, 100vw)', height: '100%', background: 'var(--dsw-alias-bg-base, white)', display: 'flex', flexDirection: 'column' } },
        h('header', { style: { ...panel, display: 'flex', justifyContent: 'space-between' } },
          h('strong', null, 'DSH Runtime'), h('button', { type: 'button', 'aria-label': '关闭', style: button, onClick: () => setOpen(false) }, '×')),
        h('div', { style: panel }, `任务状态：${manifest.status}　模型审查判决：${manifest.verification.verdict}`),
        ready.relocation && h('div', { style: panel },
          `历史证据副本：复制哈希已核对（${ready.relocation.createdAt}）。此校验只证明副本与迁移收据一致，不证明原始任务或审查正确。`),
        h('nav', { 'aria-label': 'DSH Runtime', style: { display: 'flex', padding: '0 16px' } },
          Object.entries(labels).map(([name, label]) => h('button', { key: name, type: 'button',
            'aria-current': tab === name ? 'page' : undefined,
            style: { ...button, borderBottom: tab === name ? '2px solid currentColor' : 'none' },
            onClick: () => setTab(name) }, label))),
        h('div', { style: { ...panel, flex: 1 } }, body))), document.body))
    }

    return {
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('tool.call.toolview', () => ctx.slots.register(
          { name: 'tool.call.toolview', key: 'dsh_runtime', locale: 'conversation' }, EvidenceRow))
      },
    }
  },
})
