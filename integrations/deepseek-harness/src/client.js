/** Browser half of the standalone Runtime plugin. Uses only the official module table. */
window.__ModuleLoader__.load({
  id: '@dsh-runtime/harness-plugin',
  factory(require) {
    const React = require('react')
    const { createPortal } = require('react-dom')
    const h = React.createElement
    const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/
    const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/
    const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/
    const labels = { trajectory: '执行轨迹', changes: '实际变动', audit: '审计' }
    const cliRoles = { worker: '执行', reviewer: '审查', inspector: '只读检查' }
    const cliNames = { codex: 'Codex', codebuddy: 'CodeBuddy' }
    const progressAdapters = { ...cliNames, api_agent: 'API Agent' }
    const progressTools = {
      Read: '读取文件', Edit: '编辑文件', Write: '写入文件', Bash: '命令',
      commandExecution: '命令', fileChange: '文件变更', list_files: '列出文件',
      read_file: '读取文件', search_text: '搜索文件',
    }
    const loginLabels = {
      signed_in: '已登录', signed_out: '未登录', unavailable: 'CLI 不可用',
      unknown: '无法确认登录状态', unsupported: '当前宿主不支持', running: '登录窗口已打开',
    }
    const apiProviders = {
      openrouter: { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
      siliconflow: { label: 'SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
    }
    const apiMessages = {
      invalid: '连接信息无效，请检查引用、服务商和密钥格式。',
      conflict: '连接已在别处更新。请重新读取后再编辑。',
      unavailable: '连接配置不可用。请检查 Runtime 版本、连接文件和目录权限。',
      authenticated: 'OpenRouter 鉴权通过。未验证模型调用。',
      model_catalog_readable: 'SiliconFlow 聊天模型目录可读取。未验证模型调用。',
      auth_rejected: '服务商拒绝鉴权，请核对密钥或权限。',
      rate_limited: '服务商限制了请求频率。',
      redirect_rejected: '服务商返回了跳转，请核对地址。',
      http_error: '服务商返回错误，试连未通过。',
      invalid_response: '服务商返回的内容不符合试连接口预期。',
      timeout: '试连超时。',
      network_error: '试连未建立网络连接。',
      client_unavailable: 'Runtime 缺少 API 请求依赖。',
    }

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

    function drawer(title, close, ...children) {
      return createPortal(h('div', {
        style: { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgb(0 0 0 / 42%)', display: 'flex', justifyContent: 'flex-end' },
        onMouseDown: event => { if (event.target === event.currentTarget) close() },
      }, h('section', { role: 'dialog', 'aria-modal': 'true', 'aria-label': title,
        style: { width: 'min(560px, 100vw)', height: '100%', background: 'var(--dsw-alias-bg-base, white)', display: 'flex', flexDirection: 'column' },
      }, h('header', { style: { ...panel, paddingTop: 40, display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 } },
        h('button', { type: 'button', 'aria-label': '关闭', style: button, onClick: close }, '×'), h('strong', null, title)),
      ...children)), document.body)
    }

    function CliLogin({ cli, label }) {
      const [status, setStatus] = React.useState(null)
      const [busy, setBusy] = React.useState(false)
      const [message, setMessage] = React.useState('')

      async function request(operation, signal) {
        try {
          const query = new URLSearchParams({ cli, operation })
          const response = await fetch('api/dsh-runtime.cli-login?' + query, {
            method: 'POST', headers: { 'x-dsh-runtime-cli': '1' }, signal,
          })
          if (response.status === 404) return 'unsupported'
          if (response.status === 409) return 'running'
          if (response.ok) {
            const { status } = await response.json()
            if (Object.hasOwn(loginLabels, status) || status === 'closed') return status
          }
        } catch {
          // A failed check is not proof that the CLI is signed out.
        }
        return 'unknown'
      }

      async function refresh(signal) {
        setStatus(null)
        const value = await request('status', signal)
        if (!signal?.aborted) setStatus(value === 'closed' ? 'unknown' : value)
      }

      React.useEffect(() => {
        const lifetime = new AbortController()
        void refresh(lifetime.signal)
        return () => lifetime.abort()
      }, [cli])

      async function login() {
        setBusy(true)
        setMessage(cli === 'codex' ? '请在打开的窗口中完成 Codex 登录。'
          : '请在打开的 CodeBuddy 窗口中按提示登录，或输入 /login。完成后关闭窗口。')
        const result = await request('login')
        setMessage(result === 'closed' ? '窗口已关闭，正在重新检查登录状态。'
          : result === 'running' ? '已有登录窗口，请在该窗口继续。' : '未能确认登录窗口正常结束，请检查状态后再试。')
        await refresh()
        setBusy(false)
        if (result === 'closed') setMessage('')
      }

      const canLogin = status && !['unavailable', 'unsupported', 'running'].includes(status)
      return h('div', { style: { margin: '8px 0' } },
        h('p', { role: 'status' }, label + ' · ' + (status === null ? '正在检查…' : loginLabels[status])),
        h('button', { type: 'button', disabled: busy || !canLogin, onClick: login }, '打开 ' + label + ' 登录'),
        h('button', { type: 'button', style: button, disabled: busy || status === null,
          onClick: () => { setMessage(''); void refresh() } }, '刷新 ' + label + ' 状态'),
        message && h('p', { role: 'status' }, message))
    }

    function ApiConnections({ roles, inputStyle }) {
      const [catalog, setCatalog] = React.useState(null)
      const [selected, setSelected] = React.useState('')
      const [draftRef, setDraftRef] = React.useState('')
      const [draftProvider, setDraftProvider] = React.useState('openrouter')
      const [busy, setBusy] = React.useState(false)
      const [stale, setStale] = React.useState(false)
      const [message, setMessage] = React.useState('')
      const password = React.useRef(null)
      const existing = catalog?.connections.find(item => item.reference === selected)
      const reference = existing?.reference ?? draftRef
      const provider = existing?.provider ?? draftProvider

      async function send(body, signal) {
        try {
          const response = await fetch('api/dsh-runtime.api-connections', {
            method: 'POST', cache: 'no-store', signal,
            headers: { 'content-type': 'application/json', 'x-dsh-runtime-api': '1' },
            body: JSON.stringify(body),
          })
          return await response.json()
        } catch {
          return { status: 'unavailable' }
        }
      }

      async function refresh(signal) {
        setBusy(true)
        const result = await send({ action: 'list' }, signal)
        if (signal?.aborted) return
        setBusy(false)
        if (result?.status !== 'ok') {
          setStale(true)
          setMessage(apiMessages.unavailable)
          return
        }
        if (password.current) password.current.value = ''
        setSelected('')
        setDraftRef('')
        setCatalog(result)
        setStale(false)
        setMessage('')
      }

      React.useEffect(() => {
        const lifetime = new AbortController()
        void refresh(lifetime.signal)
        return () => lifetime.abort()
      }, [])

      async function submit(action) {
        const key = password.current?.value || null
        if (!catalog || busy || stale) return
        if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/u.test(reference)
          || (key !== null && !/^[\x21-\x7e]{8,512}$/u.test(key))) {
          setMessage(apiMessages.invalid)
          return
        }
        if (!existing && catalog.connections.some(item => item.reference === reference)) {
          setMessage('该连接引用已存在，请从列表选择它再编辑。')
          return
        }
        if (!existing && key === null) {
          setMessage('新连接需要填写 API Key。')
          return
        }
        setBusy(true)
        setMessage(action === 'test' ? '正在试连…' : '正在保存…')
        const result = await send({ action, reference, provider, key, revision: catalog.revision })
        setBusy(false)
        if (action === 'save' && result?.status === 'ok') {
          if (password.current) password.current.value = ''
          setCatalog(result)
          setSelected(reference)
          setDraftRef('')
          setMessage('连接已保存。新任务会读取更新后的凭据。')
          return
        }
        if (result?.status === 'conflict') setStale(true)
        setMessage(apiMessages[result?.status] ?? apiMessages.unavailable)
      }

      const disabled = !catalog || busy || stale
      const attached = Object.entries(roles)
        .filter(([, role]) => role.adapter === 'api_agent' && role.connection_ref === reference)
        .map(([role, value]) => cliRoles[role] + ' · ' + value.model)
      return h('section', { 'aria-label': 'API 连接', style: { paddingTop: 18 } },
        h('strong', null, 'API 连接'),
        h('p', null, '试连使用当前表单，不会保存或发起推理。角色继续使用 Profile 中的连接引用和模型。'),
        h('label', null, '已保存的 API 连接', h('select', { style: inputStyle, value: selected,
          disabled, onChange: event => { setSelected(event.target.value); setDraftRef(''); setMessage('') },
        }, h('option', { value: '' }, '新建 API 连接'),
        ...(catalog?.connections ?? []).map(item => h('option', { key: item.reference, value: item.reference },
          item.reference + ' · ' + apiProviders[item.provider].label)))),
        h('label', null, '连接引用', h('input', { style: inputStyle, value: reference, maxLength: 64,
          disabled: disabled || Boolean(existing), spellCheck: false, autoComplete: 'off',
          onChange: event => setDraftRef(event.target.value) })),
        h('label', null, 'API 服务商', h('select', { style: inputStyle, value: provider,
          disabled: disabled || Boolean(existing), onChange: event => { setDraftProvider(event.target.value); setMessage('') },
        }, ...Object.entries(apiProviders).map(([id, item]) => h('option', { key: id, value: id }, item.label)))),
        h('p', null, '服务地址：' + apiProviders[provider].url),
        existing && h('p', null, 'API Key 已设置。留空保留已保存的密钥。'),
        attached.length > 0 && h('p', null, '使用此连接的角色与模型：' + attached.join('，')),
        h('label', null, 'API Key', h('input', { key: selected + provider, ref: password, type: 'password',
          maxLength: 512, autoComplete: 'new-password', spellCheck: false, style: inputStyle, disabled })),
        h('button', { type: 'button', disabled, onClick: () => void submit('save') }, '保存 API 连接'),
        h('button', { type: 'button', disabled, style: button, onClick: () => void submit('test') }, '试连 API'),
        h('button', { type: 'button', disabled: busy, style: button, onClick: () => void refresh() }, '重新读取 API 连接'),
        h('p', { role: 'status' }, message || (!catalog && busy ? '正在读取 API 连接…' : '')))
    }

    function RoleDefaults({ form, mirror }) {
      const snapshot = React.useSyncExternalStore(listener => mirror.subscribe(listener), () => mirror.getSnapshot())
      const entry = snapshot.view?.namespaces.find(item => item.ns === 'dsh-runtime-standalone')
      const [edit, setEdit] = React.useState(null)
      const [saving, setSaving] = React.useState(false)
      const [message, setMessage] = React.useState('')
      const configured = entry?.value?.roleConfig
      const current = configured === undefined ? { schema_version: 1, roles: {
        worker: { adapter: 'codebuddy', model: null },
        reviewer: { adapter: 'codex', model: null },
        inspector: { adapter: 'codex', model: null },
      } } : configured
      const roles = edit?.roles ?? current?.roles
      const stale = edit !== null && edit.revision !== entry?.revision
      const inputStyle = { display: 'block', width: '100%', maxWidth: 420, margin: '4px 0 8px',
        boxSizing: 'border-box', padding: '6px 8px', borderRadius: 4,
        border: '1px solid var(--dsw-alias-border-normal, #888)', background: 'var(--dsw-alias-bg-base, white)', color: 'inherit' }

      if (!entry || !entry.value || typeof entry.revision !== 'number') {
        return h('p', null, snapshot.view ? '当前宿主未提供模型配置。' : '正在读取 Runtime 默认配置…')
      }
      if (!roles || !current || ![1, 2].includes(current.schema_version)) {
        return h('p', null, '当前角色配置无法在此处编辑。')
      }
      const valid = Object.keys(cliRoles).every(role => {
        const selected = roles[role]
        if (!selected) return false
        if (selected.adapter === 'api_agent') return role !== 'worker' && current.schema_version === 2
        return (selected.adapter === 'codex' || (role === 'worker' && selected.adapter === 'codebuddy'))
          && (selected.model === null || (typeof selected.model === 'string' && MODEL_ID.test(selected.model)))
      })
      const disabled = saving || !snapshot.view.writable || stale
      const change = (role, fields) => {
        setEdit(previous => {
          const base = previous ?? { revision: entry.revision, roles: current.roles }
          return { ...base, roles: { ...base.roles, [role]: { ...base.roles[role], ...fields } } }
        })
        setMessage('')
      }
      const operations = () => {
        if (configured === undefined) return [{ op: 'set', path: ['roleConfig'], value: { schema_version: 1, roles } }]
        return Object.keys(cliRoles).flatMap(role => {
          if (current.roles[role].adapter === 'api_agent') return []
          return ['adapter', 'model'].filter(field => roles[role][field] !== current.roles[role][field])
            .map(field => ({ op: 'set', path: ['roleConfig', 'roles', role, field], value: roles[role][field] }))
        })
      }

      async function save() {
        if (!edit || disabled || !valid) return
        const ops = operations()
        if (!ops.length) {
          setEdit(null)
          return
        }
        setSaving(true)
        setMessage('')
        try {
          const accepted = await form.mutate(ops, edit.revision)
          if (accepted) {
            setEdit(null)
            setMessage('已保存。新任务使用这套默认配置，已启动的任务继续使用原配置。')
          } else {
            setMessage('宿主拒绝保存。草稿已保留，请核对当前配置后再试。')
          }
        } catch {
          setMessage('保存结果未能确认。草稿已保留，请重新读取配置。')
        } finally {
          setSaving(false)
        }
      }

      return h('section', { 'aria-label': '默认 CLI 与模型', style: { padding: '12px 0' } },
        h('strong', null, '默认 CLI 与模型'),
        h('p', null, '保存后用于新启动的 Runtime 任务。模型留空时使用所选 CLI 的默认设置。'),
        ...Object.entries(cliRoles).map(([role, label]) => {
          const selected = roles[role]
          if (!selected) return null
          if (selected.adapter === 'api_agent') {
            return h('p', { key: role }, `${label}阶段使用现有 API 角色，设置由 Profile 管理。`)
          }
          return h('div', { key: role },
            role === 'worker' && h('label', null, '执行阶段 CLI', h('select', {
              value: selected.adapter, disabled, style: inputStyle,
              onChange: event => change(role, { adapter: event.target.value, model: null }),
            }, h('option', { value: 'codebuddy' }, 'CodeBuddy'), h('option', { value: 'codex' }, 'Codex'))),
            h('label', null, `${label}阶段模型 ID${role === 'worker' ? '' : '（Codex）'}`,
              h('input', { type: 'text', value: selected.model ?? '', maxLength: 129, style: inputStyle,
                placeholder: '留空使用 CLI 默认', spellCheck: false, autoComplete: 'off', disabled,
                onChange: event => change(role, { model: event.target.value || null }) })))
        }),
        !valid && h('p', { role: 'alert' }, '模型 ID 须以字母或数字开头，最多 128 字符。可以使用字母、数字和 . _ : / + -。'),
        stale && h('p', { role: 'alert' }, '配置已在别处更新。请重新读取后再编辑。'),
        h('button', { type: 'button', disabled: disabled || !edit || !valid, onClick: save }, saving ? '正在保存…' : '保存默认配置'),
        edit && h('button', { type: 'button', style: button, disabled: saving, onClick: () => {
          setEdit(null)
          setMessage('')
        } }, '放弃草稿并读取当前值'),
        h('p', { role: 'status' }, message),
        window.location?.protocol === 'dsh-app:' && h(React.Fragment, null,
          h('section', { 'aria-label': 'CLI 登录', style: { paddingTop: 12 } },
            h('strong', null, 'CLI 登录'),
            h('p', null, '登录由各 CLI 完成。Codex 使用 Runtime 专用登录目录。'),
            ...Object.entries(cliNames).map(([cli, label]) => h(CliLogin, { key: cli, cli, label }))),
          h(ApiConnections, { roles: current.roles, inputStyle })))
    }

    function failureGuidance(state, manifest) {
      if (!manifest) {
        return ['aborted', 'error', 'unavailable'].includes(state)
          ? '缺少终态证据，无法确认文件是否发生变动。请先手动核对工作区。' : null
      }
      if (manifest.task_kind !== 'repository_change') return null
      const { verdict, invocation_binding: binding } = manifest.verification
      if (verdict === 'FAIL' && manifest.status === 'failed') {
        return '模型审查未通过。请先查看审计中的审查原文，并核对「实际变动」。'
      }
      if (verdict !== 'UNAVAILABLE') return null
      const reason = binding === 'missing' ? '缺少审查调用记录'
        : binding === 'invalid' ? '审查调用证据未通过绑定校验' : '现有证据无法形成有效的审查判决'
      return `${reason}。请查看「审计」和「实际变动」，必要时手动核对工作区。`
    }

    function modelLines(manifest) {
      if (manifest.task_kind !== 'repository_change') return []
      const models = manifest.model_observations
      const legacy = models?.version === 1 && models.source === 'codex_thread_start'
      const entries = (legacy || models?.version === 2)
        && Array.isArray(models.entries) && models.entries.length <= 2 ? models.entries : []
      const validId = value => value === null || (typeof value === 'string' && MODEL_ID.test(value))
      return ['worker', 'reviewer'].map((role, index) => {
        const title = index === 0 ? '执行阶段模型' : '审查阶段模型'
        const matches = entries.filter(entry => entry?.role === role)
        const entry = matches[0]
        if (matches.length !== 1 || entry.invocation_index !== index + 1
          || !validId(entry.requested_model) || !validId(entry.reported_model)) {
          return line(title, '未记录')
        }
        const source = legacy ? models.source : entry.source
        const codex = entry.adapter === 'codex' && source === 'codex_thread_start'
        const codebuddy = index === 0 && entry.adapter === 'codebuddy' && source ===
          (entry.reported_model === null ? 'unobserved' : 'codebuddy_json_assistant')
        if (!codex && !codebuddy) return line(title, '未记录')
        const requested = entry.requested_model ?? 'CLI 默认'
        const reported = entry.reported_model ?? '未知'
        const mismatch = entry.requested_model !== null && entry.reported_model !== null
          && entry.requested_model !== entry.reported_model ? '（与请求不同）' : ''
        const adapter = codex ? 'Codex' : 'CodeBuddy'
        const reportLabel = codex ? 'CLI 启动返回'
          : source === 'codebuddy_json_assistant' ? 'CLI JSON 报告' : 'CLI 报告'
        return line(title, `${adapter} · 请求 ${requested} · ${reportLabel} ${reported}${mismatch}`)
      })
    }

    function liveActivity(progress, now) {
      const item = progress?.activity
      if (!item || !Object.hasOwn(progressAdapters, item.adapter) || !Number.isSafeInteger(item.atMs)) return null
      let message
      if (item.kind === 'tool' && Object.hasOwn(progressTools, item.tool)) {
        const status = { called: '已发起', completed: '已完成', failed: '失败' }
        if (Object.hasOwn(status, item.status)) message = progressTools[item.tool] + ' · ' + status[item.status]
      } else if (item.kind === 'started') message = '执行器已启动'
      else if (item.kind === 'model') message = '收到模型活动'
      else if (item.kind === 'finishing') message = '收到执行器结束事件'
      if (!message) return null
      const seconds = Math.max(0, Math.floor((now - item.atMs) / 1000))
      return '最近事件 · ' + progressAdapters[item.adapter] + ' · ' + message + ' · ' + seconds + ' 秒前'
    }

    function EvidenceRow(props) {
      const id = startedChild(props)
      const [state, setState] = React.useState('waiting')
      const [open, setOpen] = React.useState(false)
      const [tab, setTab] = React.useState('trajectory')
      const [now, setNow] = React.useState(Date.now())
      const [progress, setProgress] = React.useState(null)
      const start = props.phase === 'result' ? props.block.callTime ?? props.block.time : props.block.time

      React.useEffect(() => {
        setState('waiting')
        setProgress(null)
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
            } else {
              setProgress(value.progress ?? {})
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
      const guidance = failureGuidance(state, manifest)
      const active = state === 'waiting' && progress?.phase
      const stage = active && Object.hasOwn(cliRoles, active.role) && Object.hasOwn(progressAdapters, active.adapter)
        ? cliRoles[active.role] + '阶段 · ' + progressAdapters[active.adapter] : '运行中'
      const elapsed = Math.max(0, Math.round((now - start) / 1000))
      const summary = ready ? `${manifest.status} · ${Math.round(manifest.duration_ms / 1000)} 秒${ready.relocation ? ' · 历史证据副本' : ''}`
        : state === 'waiting' ? (id ? (progress ? stage : '等待证据') + ' · ' + elapsed + ' 秒' : '正在启动')
          : state === 'aborted' ? '已取消'
            : state === 'error' ? '运行失败' : '终态证据不可用'
      let body = null
      if (ready && tab === 'trajectory') {
        const trajectory = manifest.execution_trajectory
        body = [line('轨迹状态', trajectory.status), line('轮次', trajectory.turns_used ?? '未记录'),
          ...modelLines(manifest),
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
        body = [line('审计状态', manifest.audit.status),
          guidance && typeof manifest.run_id === 'string' && RUN_ID.test(manifest.run_id)
            ? line('运行 ID', manifest.run_id) : null,
          line('调用 ID', manifest.audit.call_id),
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
          ready && h('button', { type: 'button', style: button, onClick: () => {
            if (guidance) setTab('audit')
            setOpen(true)
          } }, '查看证据')),
        guidance && h('p', { style: { fontSize: 12, margin: '4px 0' } }, guidance),
        state === 'waiting' && progress && h('p', { style: { fontSize: 12, margin: '4px 0' } },
          liveActivity(progress, now) ?? '等待可显示的运行事件'),
        open && ready && drawer('DSH Runtime', () => setOpen(false),
        h('div', { style: panel }, `任务状态：${manifest.status}　模型审查判决：${manifest.verification.verdict}`),
        guidance && h('p', { style: panel }, guidance),
        ready.relocation && h('div', { style: panel },
          `历史证据副本：复制哈希已核对（${ready.relocation.createdAt}）。此校验只证明副本与迁移收据一致，不证明原始任务或审查正确。`),
        h('nav', { 'aria-label': 'DSH Runtime', style: { display: 'flex', padding: '0 16px' } },
          Object.entries(labels).map(([name, label]) => h('button', { key: name, type: 'button',
            'aria-current': tab === name ? 'page' : undefined,
            style: { ...button, borderBottom: tab === name ? '2px solid currentColor' : 'none' },
            onClick: () => setTab(name) }, label))),
        h('div', { style: { ...panel, flex: 1 } }, body)))
    }

    return {
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('tool.call.toolview', () => ctx.slots.register(
          { name: 'tool.call.toolview', key: 'dsh_runtime', locale: 'conversation' }, EvidenceRow))
        ctx.inject(['configForms'], child => {
          const form = child.configForms.get('dsh-runtime-standalone')
          const mirror = child.configForms.describe()
          child.slots.inject('plugins.bundle.config', () => child.slots.register({
            name: 'plugins.bundle.config', key: '@dsh-runtime/harness-plugin',
          }, () => h(RoleDefaults, { form, mirror })))
        })
      },
    }
  },
})
