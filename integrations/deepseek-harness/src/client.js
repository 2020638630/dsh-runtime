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
    const modelMessages = {
      signed_out: '请先在插件页登录 Codex。',
      running: 'CLI 登录窗口仍在运行，请关闭后再刷新。',
      unsupported: '当前 CLI 版本未提供可读取的模型列表。',
      missing_connection: '请先保存此角色绑定的 API 连接。',
      conflict: '连接已更新，请先重新读取 API 连接。',
      busy: '正在读取其他模型列表，请稍后刷新。',
      auth_rejected: apiMessages.auth_rejected,
      rate_limited: apiMessages.rate_limited,
      timeout: '读取模型列表超时。',
      network_error: '未能连接服务商读取模型列表。',
    }
    const MODEL_CACHE_MS = 5 * 60 * 1000

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

    const runButton = {
      border: '1px solid var(--dsw-alias-border-l3, currentColor)', borderRadius: 8,
      background: 'transparent', color: 'inherit', cursor: 'pointer', padding: '5px 10px',
    }
    const runStatuses = {
      completed: '已完成', failed: '运行失败', timed_out: '运行超时', max_iterations: '已达运行轮次上限',
    }
    const evidenceStatuses = {
      available: '可用', unavailable: '不可用', incomplete: '不完整', unknown: '未知',
      not_applicable: '不适用', settled: '已结算', invalid: '校验失败',
    }
    const labelFor = (labels, value) => Object.hasOwn(labels, value) ? labels[value] : '未知'
    const line = (label, value) => h('p', { key: label }, `${label}：${value ?? '未知'}`)
    const disclosure = (title, ...children) =>
      h('details', { key: title }, h('summary', null, title), ...children)
    const evidenceCss = `
      .dsh-runtime-evidence {
        --rt-surface: var(--dsw-alias-bg-base, Canvas);
        --rt-muted: var(--dsw-alias-label-secondary, CanvasText);
        --rt-line: var(--dsw-alias-border-l3, color-mix(in srgb, CanvasText 24%, transparent));
        --rt-focus: var(--dsw-alias-link, Highlight);
        box-sizing: border-box; position: fixed; inset: 0 0 0 auto; margin: 0;
        width: min(560px, 100%); height: 100%; max-width: 100%; max-height: 100%;
        padding: 0; border: 0; border-inline-start: 1px solid var(--rt-line);
        color: var(--dsw-alias-label-primary, CanvasText); background: var(--rt-surface);
        line-height: 1.45; overflow: hidden; overflow-wrap: anywhere;
      }
      .dsh-runtime-evidence[open] { display: flex; flex-direction: column; }
      .dsh-runtime-evidence::backdrop { background: rgb(0 0 0 / 42%); }
      .dsh-runtime-evidence :where(p, h2, dt, dd) { margin: 0; }
      .dsh-runtime-evidence :where(button, summary, .rt-evidence-body):focus-visible {
        outline: 2px solid var(--rt-focus); outline-offset: -2px;
      }
      .dsh-runtime-evidence .rt-evidence-head {
        display: flex; align-items: center; gap: 12px; justify-content: space-between;
        padding: 38px 16px 12px; flex: none; border-bottom: 1px solid var(--rt-line);
      }
      .dsh-runtime-evidence h2 { font-size: 17px; font-weight: 650; }
      .dsh-runtime-evidence .rt-evidence-body { min-height: 0; overflow: auto; padding: 16px; }
      .dsh-runtime-evidence .rt-evidence-summary {
        margin: 0 0 12px; display: grid; gap: 8px;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .dsh-runtime-evidence .rt-evidence-summary div,
      .dsh-runtime-evidence details, .dsh-runtime-evidence .rt-evidence-note {
        min-width: 0; padding: 8px 10px; border: 1px solid var(--rt-line); border-radius: 8px;
      }
      .dsh-runtime-evidence dt { color: var(--rt-muted); font-size: 12px; }
      .dsh-runtime-evidence dd { margin-top: 3px; font-weight: 650; }
      .dsh-runtime-evidence .rt-evidence-note { margin: 0 0 10px; font-size: 13px; }
      .dsh-runtime-evidence nav {
        display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
        padding-block: 6px; border-bottom: 1px solid var(--rt-line);
      }
      .dsh-runtime-evidence nav [aria-current="page"] {
        border-color: currentColor; font-weight: 650;
        background: color-mix(in srgb, currentColor 9%, transparent);
      }
      .dsh-runtime-evidence .rt-evidence-content { display: grid; gap: 8px; font-size: 13px; }
      .dsh-runtime-evidence summary { cursor: pointer; }
      .dsh-runtime-evidence details p { margin-top: 8px; }
      .dsh-runtime-evidence pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
      .dsh-runtime-evidence .rt-review-summary { margin-bottom: 10px; }
      .dsh-runtime-evidence .rt-review-summary textarea {
        display: block; box-sizing: border-box; width: 100%; min-height: 9rem; margin: 8px 0;
        padding: 8px; border: 1px solid var(--rt-line); border-radius: 6px; resize: vertical;
        background: var(--rt-surface); color: inherit; font: inherit; font-size: 12px;
      }
      .dsh-runtime-evidence .rt-review-summary textarea:focus-visible { outline: 2px solid var(--rt-focus); }
      @media (max-width: 360px) {
        .dsh-runtime-evidence .rt-evidence-summary { grid-template-columns: minmax(0, 1fr); }
      }
    `
    const settingsCss = `
      .dsh-runtime-settings {
        --rt-surface: var(--dsw-alias-bg-base, Canvas);
        --rt-subtle: var(--dsw-alias-bg-module-platform, color-mix(in srgb, CanvasText 5%, Canvas));
        --rt-line: var(--dsw-alias-border-l3, color-mix(in srgb, CanvasText 18%, transparent));
        --rt-control-line: color-mix(in srgb, var(--dsw-alias-label-primary, CanvasText) 46%, var(--rt-surface));
        --rt-muted: var(--dsw-alias-label-secondary, CanvasText);
        --rt-fill: var(--dsw-alias-button-primary-fill, CanvasText);
        --rt-on-fill: var(--dsw-alias-label-primary-foreground, Canvas);
        --rt-focus: var(--dsw-alias-link, Highlight);
        container: dsh-runtime-settings / inline-size;
        display: grid; gap: 16px; width: 100%; max-width: 760px; padding-block: 8px 16px;
        line-height: 1.45; overflow-wrap: anywhere;
      }
      .dsh-runtime-settings :where(p, h3, h4) { margin: 0; }
      .dsh-runtime-settings .rt-card {
        min-width: 0; padding: 18px 20px; border: 1px solid var(--rt-line);
        border-radius: 14px; background: var(--rt-surface); display: grid; gap: 14px;
      }
      .dsh-runtime-settings .rt-card h3 { font-size: 16px; font-weight: 650; }
      .dsh-runtime-settings .rt-card h4 { font-size: 14px; font-weight: 650; }
      .dsh-runtime-settings .rt-note { color: var(--rt-muted); font-size: 12px; }
      .dsh-runtime-settings .rt-head { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; }
      .dsh-runtime-settings .rt-head p { margin-top: 4px; }
      .dsh-runtime-settings .rt-chip {
        display: inline-flex; align-items: center; gap: 6px; width: fit-content;
        max-width: 100%; padding: 3px 8px; border-radius: 7px; font-size: 12px; background: var(--rt-subtle);
      }
      .dsh-runtime-settings .rt-status-dot {
        width: 8px; height: 8px; box-sizing: border-box; border: 1.5px solid currentColor;
        border-radius: 50%; flex: none;
      }
      .dsh-runtime-settings .rt-chip[data-ready] .rt-status-dot {
        color: var(--dsw-alias-state-success-primary, currentColor); background: currentColor;
      }
      .dsh-runtime-settings .rt-role {
        display: grid; grid-template-columns: minmax(120px, .75fr) minmax(0, 1.65fr);
        align-items: start; gap: 12px 20px; padding-block: 13px; border-top: 1px solid var(--rt-line);
      }
      .dsh-runtime-settings .rt-stack { min-width: 0; display: grid; gap: 6px; }
      .dsh-runtime-settings .rt-field { min-width: 0; display: grid; gap: 5px; font-size: 12px; font-weight: 550; }
      .dsh-runtime-settings .rt-control {
        box-sizing: border-box; width: 100%; min-width: 0; min-height: 34px;
        padding: 6px 9px; border: 1px solid var(--rt-control-line); border-radius: 8px;
        background: var(--rt-surface); color: inherit; font: inherit; font-size: 13px; font-weight: 400;
      }
      .dsh-runtime-settings .rt-control[aria-invalid="true"] { border-color: var(--dsw-alias-state-error-primary, currentColor); }
      .dsh-runtime-settings :where(.rt-control, .rt-btn, summary):focus-visible {
        outline: 2px solid var(--rt-focus); outline-offset: 2px;
      }
      .dsh-runtime-settings .rt-control::placeholder { color: var(--rt-muted); opacity: 1; }
      .dsh-runtime-settings .rt-control:disabled {
        opacity: 1; color: var(--rt-muted); -webkit-text-fill-color: var(--rt-muted);
        background: var(--rt-subtle);
      }
      .dsh-runtime-settings .rt-btn {
        min-height: 32px; padding: 5px 11px; border: 1px solid var(--rt-control-line); border-radius: 8px;
        background: var(--rt-surface); color: inherit; font: inherit; font-size: 12px; font-weight: 550;
        cursor: pointer; text-align: center;
      }
      .dsh-runtime-settings .rt-btn-primary {
        border-color: transparent; background: var(--rt-fill); color: var(--rt-on-fill);
      }
      .dsh-runtime-settings .rt-btn-quiet { border-color: transparent; background: transparent; color: var(--rt-muted); }
      .dsh-runtime-settings .rt-btn:hover:not(:disabled) { filter: brightness(.93); }
      .dsh-runtime-settings .rt-btn:disabled { cursor: default; opacity: .55; }
      .dsh-runtime-settings .rt-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; }
      .dsh-runtime-settings .rt-actions-end { justify-content: flex-end; }
      .dsh-runtime-settings .rt-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
      .dsh-runtime-settings .rt-login { padding-block: 10px; border-top: 1px solid var(--rt-line); }
      .dsh-runtime-settings .rt-login-name { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
      .dsh-runtime-settings .rt-grid {
        min-width: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px;
      }
      .dsh-runtime-settings .rt-span { grid-column: 1 / -1; }
      .dsh-runtime-settings .rt-directory {
        min-width: 0; border: 1px solid var(--rt-line); border-radius: 8px; background: var(--rt-subtle);
      }
      .dsh-runtime-settings .rt-directory summary { padding: 6px 9px; cursor: pointer; font-size: 12px; }
      .dsh-runtime-settings .rt-directory-body { padding: 3px 9px 9px; }
      .dsh-runtime-settings .rt-notice { padding: 7px 9px; border-radius: 8px; background: var(--rt-subtle); font-size: 12px; }
      .dsh-runtime-settings .rt-notice:empty { display: none; }
      @container dsh-runtime-settings (max-width: 500px) {
        .dsh-runtime-settings .rt-card { padding: 14px; }
        .dsh-runtime-settings .rt-role, .dsh-runtime-settings .rt-grid { grid-template-columns: minmax(0, 1fr); }
      }
    `
    const settingsHeader = (title, help, status) => h('header', { className: 'rt-head' },
      h('div', null, h('h3', null, title), h('p', { className: 'rt-note' }, help)), status)
    const field = (label, control, full = false) =>
      h('label', { className: full ? 'rt-field rt-span' : 'rt-field' }, label, control)

    function CliLogin({ cli, label, invalidateModels }) {
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
        invalidateModels()
        setBusy(true)
        setMessage(cli === 'codex' ? '请在打开的窗口中完成 Codex 登录。'
          : '请在打开的 CodeBuddy 窗口中按提示登录，或输入 /login。完成后关闭窗口。')
        const result = await request('login')
        invalidateModels()
        setMessage(result === 'closed' ? '窗口已关闭，正在重新检查登录状态。'
          : result === 'running' ? '已有登录窗口，请在该窗口继续。' : '未能确认登录窗口正常结束，请检查状态后再试。')
        await refresh()
        setBusy(false)
        if (result === 'closed') setMessage('')
      }

      const canLogin = status && !['unavailable', 'unsupported', 'running'].includes(status)
      const loginLabel = status === 'signed_in' ? '管理 ' + label + ' 登录' : '打开 ' + label + ' 登录'
      return h('div', { className: 'rt-login rt-stack' },
        h('div', { className: 'rt-footer' },
          h('div', { className: 'rt-login-name' }, h('h4', null, label),
            h('span', { className: 'rt-chip', role: 'status', 'data-ready': status === 'signed_in' ? '' : undefined },
              h('span', { className: 'rt-status-dot', 'aria-hidden': 'true' }),
              status === null ? '正在检查…' : loginLabels[status])),
          h('div', { className: 'rt-actions' },
            h('button', { type: 'button', className: 'rt-btn', disabled: busy || !canLogin, onClick: login }, loginLabel),
            h('button', { type: 'button', className: 'rt-btn rt-btn-quiet', disabled: busy || status === null,
              'aria-label': '刷新 ' + label + ' 状态',
              onClick: () => { invalidateModels(); setMessage(''); void refresh() } }, '刷新状态'))),
        h('p', { className: 'rt-notice', role: 'status' }, message))
    }

    function ApiConnections({ roles, onRevision }) {
      const [catalog, setCatalog] = React.useState(null)
      const [selected, setSelected] = React.useState('')
      const [draftRef, setDraftRef] = React.useState('')
      const [draftProvider, setDraftProvider] = React.useState('openrouter')
      const [busy, setBusy] = React.useState(false)
      const [stale, setStale] = React.useState(false)
      const [notice, setNotice] = React.useState(null)
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

      async function refresh({ signal, announce = false } = {}) {
        onRevision(null)
        setBusy(true)
        setNotice(announce ? { section: 'catalog', text: '正在重新读取连接…' } : null)
        const result = await send({ action: 'list' }, signal)
        if (signal?.aborted) return
        setBusy(false)
        if (result?.status !== 'ok') {
          setStale(true)
          setNotice({ section: 'catalog', text: apiMessages.unavailable })
          return
        }
        if (password.current) password.current.value = ''
        setSelected('')
        setDraftRef('')
        setCatalog(result)
        onRevision(result.revision)
        setStale(false)
        setNotice(announce ? { section: 'catalog', text: `已读取 ${result.connections.length} 条连接。` } : null)
      }

      React.useEffect(() => {
        const lifetime = new AbortController()
        void refresh({ signal: lifetime.signal })
        return () => lifetime.abort()
      }, [])

      async function submit(action) {
        const key = password.current?.value || null
        if (!catalog || busy || stale) return
        const report = text => setNotice({ section: 'actions', text })
        if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/u.test(reference)
          || (key !== null && !/^[\x21-\x7e]{8,512}$/u.test(key))) {
          report(apiMessages.invalid)
          return
        }
        if (!existing && catalog.connections.some(item => item.reference === reference)) {
          report('该连接引用已存在，请从列表选择它再编辑。')
          return
        }
        if (!existing && key === null) {
          report('新连接需要填写 API Key。')
          return
        }
        setBusy(true)
        report(action === 'test' ? '正在试连…' : '正在保存…')
        const result = await send({ action, reference, provider, key, revision: catalog.revision })
        setBusy(false)
        if (action === 'save' && result?.status === 'ok') {
          if (password.current) password.current.value = ''
          setCatalog(result)
          onRevision(result.revision)
          setSelected(reference)
          setDraftRef('')
          report('连接已保存。新任务会读取更新后的凭据。')
          return
        }
        if (result?.status === 'conflict') {
          setStale(true)
          onRevision(null)
        }
        report(apiMessages[result?.status] ?? apiMessages.unavailable)
      }

      const disabled = !catalog || busy || stale
      const attached = Object.entries(roles)
        .filter(([, role]) => role.adapter === 'api_agent' && role.connection_ref === reference)
        .map(([role, value]) => cliRoles[role] + ' · ' + value.model)
      return h('section', { 'aria-label': 'API 连接', className: 'rt-card' },
        settingsHeader('API 连接', '管理连接与密钥。试连使用当前表单，不会保存或发起推理。',
          h('button', { type: 'button', className: 'rt-btn rt-btn-quiet', disabled: busy,
            onClick: () => void refresh({ announce: true }) }, '重新读取连接')),
        h('p', { className: 'rt-notice', role: 'status' }, notice?.section === 'catalog' ? notice.text
          : !catalog && busy ? '正在读取 API 连接…' : ''),
        h('div', { className: 'rt-grid' },
        field('已保存的 API 连接', h('select', { className: 'rt-control', value: selected,
          disabled, onChange: event => { setSelected(event.target.value); setDraftRef(''); setNotice(null) },
        }, h('option', { value: '' }, '新建 API 连接'),
        ...(catalog?.connections ?? []).map(item => h('option', { key: item.reference, value: item.reference },
          item.reference + ' · ' + apiProviders[item.provider].label))), true),
        field('连接引用', h('input', { className: 'rt-control', value: reference, maxLength: 64,
          disabled: disabled || Boolean(existing), spellCheck: false, autoComplete: 'off',
          onChange: event => setDraftRef(event.target.value) })),
        field('API 服务商', h('select', { className: 'rt-control', value: provider,
          disabled: disabled || Boolean(existing), onChange: event => { setDraftProvider(event.target.value); setNotice(null) },
        }, ...Object.entries(apiProviders).map(([id, item]) => h('option', { key: id, value: id }, item.label)))),
        h('p', { className: 'rt-note rt-span' }, apiProviders[provider].url),
        field(existing ? 'API Key（已设置）' : 'API Key', h('input', { key: selected + provider, ref: password, type: 'password',
          maxLength: 512, autoComplete: 'new-password', spellCheck: false, className: 'rt-control',
          'aria-describedby': existing ? 'dsh-rt-key-help' : undefined,
          placeholder: existing ? '输入新密钥' : '输入密钥', disabled }), true),
        existing && h('p', { className: 'rt-note rt-span', id: 'dsh-rt-key-help' }, '留空保留已保存的密钥。'),
        attached.length > 0 && h('p', { className: 'rt-note rt-span' }, '已绑定 ' + attached.join('，'))),
        h('p', { className: 'rt-notice', role: 'status' }, notice?.section === 'actions' ? notice.text : ''),
        h('div', { className: 'rt-actions rt-actions-end' },
          h('button', { type: 'button', className: 'rt-btn', disabled, onClick: () => void submit('test') }, '试连 API'),
          h('button', { type: 'button', className: 'rt-btn rt-btn-primary', disabled,
            onClick: () => void submit('save') }, '保存 API 连接')))
    }

    function ModelOptions({ selected, label, revision, disabled, onSelect }) {
      const [state, setState] = React.useState(null)
      const [search, setSearch] = React.useState('')
      const pending = React.useRef(null)
      React.useEffect(() => () => { pending.current?.abort(); pending.current = null }, [])
      const api = selected.adapter === 'api_agent'
      const canRead = selected.adapter === 'codex' || (api && typeof revision === 'string')
      const caption = api ? '浏览 ' + apiProviders[selected.provider].label + ' 候选' : '浏览 Codex 候选'

      async function load(force) {
        if (!canRead || pending.current || (state?.status === 'ok' && !force
          && Date.now() - state.at < MODEL_CACHE_MS)) return
        const controller = new AbortController()
        pending.current = controller
        setState({ status: 'loading' })
        let result
        try {
          const response = api
            ? await fetch('api/dsh-runtime.api-connections', { method: 'POST', cache: 'no-store',
              headers: { 'content-type': 'application/json', 'x-dsh-runtime-api': '1' }, signal: controller.signal,
              body: JSON.stringify({ action: 'models', revision, reference: selected.connection_ref,
                provider: selected.provider }) })
            : await fetch('api/dsh-runtime.cli-login?cli=codex&operation=models', { method: 'POST', cache: 'no-store',
              headers: { 'x-dsh-runtime-cli': '1' }, signal: controller.signal })
          result = await response.json()
        } catch { result = { status: 'unavailable' } }
        if (pending.current !== controller || controller.signal.aborted) return
        pending.current = null
        if (result?.status === 'ok' && Array.isArray(result.models) && result.models.length <= 512
          && result.models.every(model => typeof model === 'string' && MODEL_ID.test(model))) {
          setState({ status: 'ok', models: [...new Set(result.models)], at: Date.now(), truncated: result.truncated === true })
        } else {
          setState({ status: Object.hasOwn(modelMessages, result?.status) ? result.status : 'unavailable' })
        }
      }

      if (selected.adapter === 'codebuddy') {
        return h('p', { className: 'rt-note' }, '手填模型 ID，或留空使用 CLI 默认。')
      }
      const models = state?.status === 'ok' ? state.models : []
      const query = search.trim().toLowerCase()
      const matches = models.filter(id => id.toLowerCase().includes(query))
      const detail = !canRead ? '请先保存或重新读取此角色绑定的 API 连接。'
        : state?.status === 'loading' ? '正在读取模型列表…'
          : state?.status === 'ok' ? (models.length ? `已读取 ${models.length} 个候选 · ${new Date(state.at).toLocaleTimeString()}`
            + (state.truncated ? ' · 仅显示部分候选' : '') : '模型列表为空。')
            : state ? (modelMessages[state.status] ?? '暂时无法读取模型列表。') + ' 可继续手填。' : ''
      return h('details', { className: 'rt-directory', onToggle: event => {
        if (event.currentTarget.open) void load(false)
      } }, h('summary', null, caption),
      h('div', { className: 'rt-directory-body rt-stack' },
      h('div', { className: 'rt-footer' },
        h('p', { className: 'rt-note', role: 'status' }, detail),
        h('button', { type: 'button', className: 'rt-btn', disabled: !canRead || state?.status === 'loading',
          onClick: () => void load(true) }, '刷新模型列表')),
      api && h('p', { className: 'rt-note' }, '服务商目录仅供选型参考，调用权限以实际账户为准。'),
      state?.status === 'ok' && selected.model && !models.includes(selected.model)
        && h('p', { className: 'rt-note' }, '当前配置未在列表中找到，已保留。'),
      models.length > 0 && h('div', { className: 'rt-grid' },
        field('搜索' + label + '阶段模型', h('input', { type: 'search', className: 'rt-control',
          value: search, onChange: event => setSearch(event.target.value) })),
        field('选择' + label + '阶段模型', h('select', { className: 'rt-control', value: '',
          disabled: disabled || matches.length === 0,
          onChange: event => { if (matches.includes(event.target.value)) onSelect(event.target.value) } },
        h('option', { value: '' }, matches.length ? '请选择模型' : '没有匹配的候选'),
        ...matches.map(id => h('option', { key: id, value: id }, id)))))))
    }

    function RoleDefaults({ form, mirror }) {
      const snapshot = React.useSyncExternalStore(listener => mirror.subscribe(listener), () => mirror.getSnapshot())
      const entry = snapshot.view?.namespaces.find(item => item.ns === 'dsh-runtime-standalone')
      const [edit, setEdit] = React.useState(null)
      const [saving, setSaving] = React.useState(false)
      const [message, setMessage] = React.useState('')
      const [catalogRevision, setCatalogRevision] = React.useState(null)
      const [cliEpoch, setCliEpoch] = React.useState(0)
      const desktop = window.location?.protocol === 'dsh-app:'
      const configured = entry?.value?.roleConfig
      const current = configured === undefined ? { schema_version: 1, roles: {
        worker: { adapter: 'codebuddy', model: null },
        reviewer: { adapter: 'codex', model: null },
        inspector: { adapter: 'codex', model: null },
      } } : configured
      const roles = edit?.roles ?? current?.roles
      const stale = edit !== null && edit.revision !== entry?.revision

      if (!entry || !entry.value || typeof entry.revision !== 'number') {
        return h('p', null, snapshot.view ? '当前宿主未提供模型配置。' : '正在读取 Runtime 默认配置…')
      }
      if (!roles || !current || ![1, 2].includes(current.schema_version)) {
        return h('p', null, '当前角色配置无法在此处编辑。')
      }
      const validModel = selected => (selected.adapter !== 'api_agent' && selected.model === null)
        || (typeof selected.model === 'string' && MODEL_ID.test(selected.model))
      const valid = Object.keys(cliRoles).every(role => {
        const selected = roles[role]
        if (!selected || !validModel(selected)) return false
        if (selected.adapter === 'api_agent') return role !== 'worker' && current.schema_version === 2
        return (selected.adapter === 'codex' || (role === 'worker' && selected.adapter === 'codebuddy'))
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
          const fields = current.roles[role].adapter === 'api_agent' ? ['model'] : ['adapter', 'model']
          return fields.filter(field => roles[role][field] !== current.roles[role][field])
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

      return h('div', { className: 'dsh-runtime-settings' }, h('style', null, settingsCss),
        h('section', { 'aria-label': '角色与模型', className: 'rt-card' },
        settingsHeader('角色与模型', '审查和只读检查的执行器与连接绑定由 Profile 配置管理。',
          h('span', { className: 'rt-chip' }, stale ? '配置已在别处更新' : edit ? '有未保存的更改'
            : configured === undefined ? '使用内置默认' : '当前配置')),
        h('div', null,
        ...Object.entries(cliRoles).map(([role, label]) => {
          const selected = roles[role]
          if (!selected) return null
          const api = selected.adapter === 'api_agent'
          if (api && !desktop) {
            return h('p', { key: role, className: 'rt-role' }, `${label}阶段使用现有 API 角色，设置由 Profile 管理。`)
          }
          const inputLabel = `${label}阶段模型 ID`
          const invalidModel = !validModel(selected)
          return h('div', { key: role, className: 'rt-role' },
            h('div', { className: 'rt-stack' }, h('h4', null, label),
            role === 'worker' ? field('执行器', h('select', {
              value: selected.adapter, disabled, className: 'rt-control', 'aria-label': '执行阶段 CLI',
              onChange: event => change(role, { adapter: event.target.value, model: null }),
            }, h('option', { value: 'codebuddy' }, 'CodeBuddy'), h('option', { value: 'codex' }, 'Codex')))
              : h('span', { className: 'rt-chip' }, api ? apiProviders[selected.provider].label : 'Codex'),
            api && h('p', { className: 'rt-note' }, '绑定连接 · ' + selected.connection_ref)),
            h('div', { className: 'rt-stack' },
            field('模型 ID', h('input', {
              type: 'text', value: selected.model ?? '', maxLength: 128, className: 'rt-control',
              'aria-label': inputLabel, 'aria-invalid': invalidModel || undefined,
              'aria-describedby': invalidModel ? 'dsh-rt-model-error-' + role : undefined,
              placeholder: api ? '输入模型 ID' : '留空使用 CLI 默认', spellCheck: false, autoComplete: 'off', disabled,
              onChange: event => change(role, { model: api ? event.target.value : event.target.value || null }) })),
            invalidModel && h('p', { role: 'alert', className: 'rt-note', id: 'dsh-rt-model-error-' + role },
              '请输入有效模型 ID，最多 128 字符，可使用字母、数字和 . _ : / + -。'),
            desktop && h(ModelOptions, { key: api
              ? JSON.stringify([selected.provider, selected.connection_ref, catalogRevision])
              : selected.adapter + ':' + cliEpoch,
            selected, label, revision: catalogRevision, disabled,
            onSelect: model => change(role, { model }) })))
        })),
        stale && h('p', { role: 'alert', className: 'rt-notice' }, '配置已在别处更新。请先放弃草稿并读取当前值。'),
        h('p', { role: 'status', className: 'rt-notice' }, message),
        h('div', { className: 'rt-footer' },
          h('p', { className: 'rt-note' }, '保存后用于新启动的 Runtime 任务。'),
          h('div', { className: 'rt-actions' },
            h('button', { type: 'button', className: 'rt-btn rt-btn-primary', disabled: disabled || !edit || !valid,
              onClick: save }, saving ? '正在保存…' : '保存默认配置'),
            edit && h('button', { type: 'button', className: 'rt-btn rt-btn-quiet', disabled: saving, onClick: () => {
              setEdit(null)
              setMessage('')
            } }, '放弃草稿并读取当前值')))),
        desktop && h(React.Fragment, null,
          h('section', { 'aria-label': 'CLI 登录', className: 'rt-card' },
            settingsHeader('CLI 登录', '登录由各 CLI 完成。Codex 使用 Runtime 专用登录目录。'),
            ...Object.entries(cliNames).map(([cli, label]) => h(CliLogin, { key: cli, cli, label,
              invalidateModels: () => setCliEpoch(value => value + 1) }))),
          h(ApiConnections, { roles: current.roles, onRevision: setCatalogRevision })))
    }

    function failureGuidance(state, manifest) {
      if (!manifest) {
        return ['aborted', 'error', 'unavailable', 'read-error'].includes(state)
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

    function observedModels(manifest) {
      const models = manifest.model_observations
      const legacy = models?.version === 1 && models.source === 'codex_thread_start'
      const entries = (legacy || models?.version === 2)
        && Array.isArray(models.entries) && models.entries.length <= 2 ? models.entries : []
      const validId = value => value === null || (typeof value === 'string' && MODEL_ID.test(value))
      return ['worker', 'reviewer'].map((role, index) => {
        const matches = entries.filter(entry => entry?.role === role)
        const entry = matches[0]
        if (matches.length !== 1 || entry.invocation_index !== index + 1
          || !validId(entry.requested_model) || !validId(entry.reported_model)) return null
        const source = legacy ? models.source : entry.source
        const codex = entry.adapter === 'codex' && source === 'codex_thread_start'
        const codebuddy = index === 0 && entry.adapter === 'codebuddy' && source ===
          (entry.reported_model === null ? 'unobserved' : 'codebuddy_json_assistant')
        if (!codex && !codebuddy) return null
        const adapter = codex ? 'Codex' : 'CodeBuddy'
        const reportLabel = codex ? 'CLI 启动返回'
          : source === 'codebuddy_json_assistant' ? 'CLI JSON 报告' : 'CLI 报告'
        return { adapter, reportLabel, requested: entry.requested_model, reported: entry.reported_model }
      })
    }

    function modelLines(manifest) {
      if (manifest.task_kind !== 'repository_change') return []
      return observedModels(manifest).map((entry, index) => {
        const title = index === 0 ? '执行阶段模型' : '审查阶段模型'
        if (!entry) return line(title, '未记录')
        const { adapter, reportLabel } = entry
        const requested = entry.requested ?? 'CLI 默认'
        const reported = entry.reported ?? '未知'
        const mismatch = entry.requested !== null && entry.reported !== null
          && entry.requested !== entry.reported ? '（与请求不同）' : ''
        return line(title, `${adapter} · 请求 ${requested} · ${reportLabel} ${reported}${mismatch}`)
      })
    }

    function formatReviewSummary(manifest, runId, stats, observed, relocated) {
      const inspection = manifest.task_kind === 'repository_inspection'
      const change = manifest.task_kind === 'repository_change'
      const parts = ['DSH Runtime 复核摘要',
        `本机证据引用：原会话 → 查看证据 → ${runId}`,
        `任务类型：${inspection ? '仓库只读检查' : change ? '仓库修改' : '未知'}`,
        `任务约束：${inspection ? '只读' : change ? '执行后须经独立只读复核' : '未记录'}；具体目标请核对原会话。`,
        ...stats.map(([label, value]) => `${label}：${value}`)]
      if (change) {
        for (const [index, model] of observedModels(manifest).entries()) {
          const source = model ? `${model.adapter} · ${model.reportLabel} · ${model.reported ? '已记录' : '未知'}` : '未记录'
          parts.push(`${index === 0 ? '执行' : '审查'}阶段模型来源：${source}`)
        }
      } else {
        parts.push('模型来源：未记录')
      }
      const changes = manifest.workspace_changes
      if (observed) {
        parts.push(`运行前后观察：新增 ${changes.added_files.length}，修改 ${changes.modified_files.length}，删除 ${changes.deleted_files.length}；变动归属未证明。`)
        parts.push(`补丁完整性：${changes.patch_complete === true ? '完整' : changes.patch_complete === false ? '不完整' : '未记录'}`)
      } else {
        parts.push('运行前后观察：缺少可比较的快照')
      }
      const target = manifest.target_observation
      if (target?.version === 1 && target.source === 'post_run_worktree_observation'
        && target.scope === 'dsh_controlled_snapshot_v1'
        && Number.isSafeInteger(target.file_count) && target.file_count >= 0 && target.file_count <= 20000) {
        const head = typeof target.base_commit === 'string' && /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/u.test(target.base_commit)
          ? target.base_commit : '未记录'
        parts.push(`Git 基准：${head}`)
        if (typeof target.content_sha256 === 'string' && /^[0-9a-f]{64}$/u.test(target.content_sha256)) {
          parts.push(`运行后工作树观察：${target.file_count} 个文件 · ${target.scope}`,
            `内容摘要 SHA-256：${target.content_sha256}`)
        } else {
          parts.push('运行后工作树观察：覆盖不完整，内容摘要不可用')
        }
      } else {
        parts.push('运行后工作树观察：未记录')
      }
      parts.push('实际受审快照：未绑定。当前工作区尚未重新核对。')
      if (manifest.verification.evidence_truncated === true) parts.push('审查原文：证据内仅保留部分。')
      if (relocated) parts.push('证据来源：历史副本。')
      return parts.join('\n')
    }

    function ReviewSummary({ summary }) {
      const [copyStatus, setCopyStatus] = React.useState('')
      const previewRef = React.useRef(null)
      async function copy() {
        try {
          await navigator.clipboard.writeText(summary)
          setCopyStatus('已复制复核摘要。')
        } catch {
          previewRef.current?.focus()
          previewRef.current?.select()
          setCopyStatus('自动复制不可用，已选中摘要。请按 Ctrl+C 或使用系统复制。')
        }
      }
      return h('details', { className: 'rt-review-summary' },
        h('summary', null, '复核摘要'),
        h('p', null, '可复制本机证据引用和摘要。任务原文、模型 ID、文件路径、源码和日志保留在原处。'),
        h('textarea', { 'aria-label': '复核摘要预览', ref: previewRef, readOnly: true, value: summary }),
        h('button', { type: 'button', style: runButton, onClick: copy }, '复制复核摘要'),
        copyStatus && h('p', { role: 'status' }, copyStatus))
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
      const dialogRef = React.useRef(null)
      const triggerRef = React.useRef(null)
      const start = props.phase === 'result' ? props.block?.callTime ?? props.block?.time : props.block?.time

      React.useEffect(() => {
        setState('waiting')
        setProgress(null)
        setOpen(false)
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
            if (lifetime.signal.aborted) return
            if (response.status === 404) {
              if (++missing >= 10) { done = true; setState('unavailable') }
              return
            }
            if (!response.ok && response.status !== 202) {
              done = true
              setState('read-error')
              return
            }
            const value = await response.json()
            if (lifetime.signal.aborted) return
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
            if (!lifetime.signal.aborted) { done = true; setState('read-error') }
          } finally {
            pending = false
            if (done) clearInterval(timer)
          }
        }
        const timer = setInterval(() => { void load() }, 3000)
        void load()
        return () => { lifetime.abort(); clearInterval(timer) }
      }, [id, props.sessionId])

      React.useEffect(() => {
        if (!id || state !== 'waiting') return
        const timer = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(timer)
      }, [id, state])
      const ready = typeof state === 'object' ? state : null
      const showDrawer = open && !!ready
      React.useEffect(() => {
        if (!showDrawer) return
        const dialog = dialogRef.current
        dialog.showModal()
        return () => dialog.close()
      }, [showDrawer])

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
        ? cliRoles[active.role] + '阶段 · ' + progressAdapters[active.adapter]
        : progress ? '运行中' : id ? '等待运行状态' : '正在启动'
      const status = ready ? labelFor(runStatuses, manifest.status)
        : state === 'waiting' ? stage
          : labelFor({ aborted: '已取消', error: '运行失败', unavailable: '终态证据不可用', 'read-error': '读取证据失败' }, state)
      const duration = ready ? manifest.duration_ms : id && state === 'waiting' && Number.isFinite(start)
        ? Math.max(0, now - start) : null
      const reviewVerdict = manifest?.task_kind === 'repository_inspection' ? '不适用'
        : labelFor({ PASS: 'PASS', FAIL: 'FAIL', UNAVAILABLE: '无法确认', NOT_APPLICABLE: '不适用' },
          manifest?.verification.verdict)
      const trajectoryStatus = labelFor(evidenceStatuses, manifest?.execution_trajectory.status)
      const auditStatus = labelFor(evidenceStatuses, manifest?.audit.status)
      let body = null
      if (showDrawer && tab === 'trajectory') {
        const trajectory = manifest.execution_trajectory
        body = [line('轮次', trajectory.turns_used ?? '未记录'),
          ...modelLines(manifest),
          h('ul', { key: 'tools' }, Object.entries(trajectory.tool_operations_summary ?? {})
            .map(([name, count]) => h('li', { key: name }, `${name}：${count}`)))]
      } else if (showDrawer && tab === 'changes') {
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
          observed && ready.diff ? disclosure('查看补丁',
            h('pre', null, ready.diff.slice(0, 200000)),
            ready.diff.length > 200000 && h('p', null, '补丁仅展示前 200000 个字符。')) : null]
      } else if (showDrawer) {
        const review = manifest.review_trajectory
        body = [disclosure('审计坐标',
          line('运行 ID', RUN_ID.test(manifest.run_id ?? '') ? manifest.run_id : null),
          line('调用 ID', manifest.audit.call_id),
          line('输出摘要', manifest.audit.stdout_sha256)),
          manifest.task_kind !== 'repository_inspection'
            ? line('判决范围', '模型报告；文件变化由独立快照观察，不能据此认定变动归属') : null,
          review?.source === 'api_agent_safe_event_trace'
            ? line('API 审查轨迹', review.status) : null,
          review?.source === 'api_agent_safe_event_trace' && review.terminal_reason
            ? line('API 审查终态', review.terminal_reason) : null,
          review?.source === 'api_agent_safe_event_trace' && review.failure_code
            ? line('API 审查失败类别', review.failure_code) : null,
          review?.source === 'api_agent_safe_event_trace' && review.status === 'available'
            ? h('ul', { key: 'review-tools' }, Object.entries(review.tool_operations_summary ?? {})
              .map(([name, count]) => h('li', { key: name }, `${name}：${count}`))) : null,
          manifest.verification.evidence_text
            ? disclosure('模型审查原文', h('pre', null, manifest.verification.evidence_text)) : null]
      }
      const close = () => {
        dialogRef.current?.close()
        triggerRef.current?.focus({ preventScroll: true })
        setOpen(false)
      }
      const stats = [['任务状态', status], ['模型审查判决', reviewVerdict],
        ['轨迹状态', trajectoryStatus], ['审计状态', auditStatus]]
      return h('div', { 'data-tool': 'dsh_runtime', style: { minWidth: 0, overflowWrap: 'anywhere' } },
        h('div', { style: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px', minHeight: 32 } },
          h('strong', null, 'DSH Runtime'),
          h('div', { style: { flex: '1 1 auto', minWidth: 0 } },
            h('span', { role: 'status' }, status),
            duration !== null && h('span', null, ` · ${Math.round(duration / 1000)} 秒`),
            ready?.relocation && h('span', null, ' · 历史证据副本')),
          ready && h('button', { type: 'button', ref: triggerRef, style: runButton, onClick: () => {
            setTab(guidance || manifest.status !== 'completed' ? 'audit' : 'trajectory')
            setOpen(true)
          } }, '查看证据')),
        ready && h('p', { style: { fontSize: 12, margin: '4px 0' } }, `模型审查判决：${reviewVerdict}`),
        guidance && h('p', { style: { fontSize: 12, margin: '4px 0' } }, guidance),
        state === 'waiting' && id && h('p', { style: { fontSize: 12, margin: '4px 0' } },
          liveActivity(progress, now) ?? '暂无可显示的运行事件'),
        showDrawer && createPortal(h('dialog', {
          ref: dialogRef, className: 'dsh-runtime-evidence', 'aria-label': 'DSH Runtime 证据',
          onCancel: event => { event.preventDefault(); close() },
          onClick: event => {
            if (event.target !== event.currentTarget) return
            const rect = event.currentTarget.getBoundingClientRect()
            if (event.clientX < rect.left || event.clientX >= rect.right) close()
          },
        }, h('style', null, evidenceCss),
        h('header', { className: 'rt-evidence-head' },
          h('h2', null, 'DSH Runtime 证据'),
          h('button', { type: 'button', style: runButton, autoFocus: true, onClick: close }, '关闭')),
        h('div', { className: 'rt-evidence-body', tabIndex: 0, role: 'region', 'aria-label': '证据详情' },
          h('dl', { className: 'rt-evidence-summary' }, stats.map(([label, value]) =>
            h('div', { key: label }, h('dt', null, label), h('dd', null, value)))),
          guidance && h('p', { className: 'rt-evidence-note' }, guidance),
          ready.relocation && h('p', { className: 'rt-evidence-note' },
            `历史证据副本：复制哈希已核对（${ready.relocation.createdAt}）。此校验只证明副本与迁移收据一致，不证明原始任务或审查正确。`),
          h(ReviewSummary, {
            summary: formatReviewSummary(manifest, `dsh-runtime-${id}`, stats, observed, ready.relocation),
          }),
          h('nav', { 'aria-label': '证据分类' },
            Object.entries(labels).map(([name, label]) => h('button', { key: name, type: 'button', style: runButton,
              'aria-current': tab === name ? 'page' : undefined, onClick: () => setTab(name) }, label))),
          h('div', { className: 'rt-evidence-content' }, body))), document.body))
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
