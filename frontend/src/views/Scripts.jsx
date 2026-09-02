import { useEffect, useState, useMemo } from 'react'
import { api } from '../api/client.js'

function fmtTime(s) {
  if (!s) return '-'
  const d = new Date(s)
  return d.toLocaleString('zh-CN', { hour12: false })
}

// 动作类型 → 参数表单定义（可视化编辑器用）
const ACTIONS = {
  open_url: { label: '打开网址', desc: '打开指定网页', fields: [
    { key: 'url', label: '网址', type: 'text', ph: 'https://www.example.com' }] },
  tap: { label: '点击', desc: '模拟点击屏幕坐标', fields: [
    { key: 'x', label: 'X 坐标', type: 'number', def: 500 },
    { key: 'y', label: 'Y 坐标', type: 'number', def: 500 }] },
  swipe: { label: '滑动', desc: '从起点滑到终点', fields: [
    { key: 'x1', label: '起点 X', type: 'number', def: 100 }, { key: 'y1', label: '起点 Y', type: 'number', def: 500 },
    { key: 'x2', label: '终点 X', type: 'number', def: 400 }, { key: 'y2', label: '终点 Y', type: 'number', def: 500 },
    { key: 'duration', label: '时长 ms', type: 'number', def: 300 }] },
  text: { label: '输入文字', desc: '向当前输入框输入文字', fields: [
    { key: 'value', label: '内容', type: 'text', ph: '要输入的文字' }] },
  key: { label: '按键', desc: '模拟物理按键', fields: [
    { key: 'key', label: '按键', type: 'select',
      options: ['home', 'back', 'enter', 'menu', 'volume_up', 'volume_down', 'power', 'app_switch', 'del', 'tab', 'space', 'search'], def: 'home' }] },
  wait: { label: '等待', desc: '等待指定秒数', fields: [
    { key: 'seconds', label: '秒数', type: 'number', def: 1 }] },
  install: { label: '打开应用', desc: '通过包名启动应用', fields: [
    { key: 'pkg', label: '包名', type: 'text', ph: 'com.example.app' }] },
}
const ACTION_KEYS = Object.keys(ACTIONS)

function stepSummary(s) {
  const p = s.params || {}
  switch (s.action) {
    case 'open_url': return `打开 ${p.url || ''}`
    case 'tap': return `点击 (${p.x ?? 500}, ${p.y ?? 500})`
    case 'swipe': return `滑动 (${p.x1 ?? 100},${p.y1 ?? 500}) → (${p.x2 ?? 400},${p.y2 ?? 500})，${p.duration ?? 300}ms`
    case 'text': return `输入 ${p.value || p.text || ''}`
    case 'key': return `按键 ${p.key || p.keycode || ''}`
    case 'wait': return `等待 ${p.seconds ?? 1} 秒`
    case 'install': return `打开应用 ${p.pkg || ''}`
    case 'sequence': return `序列 ${(p.steps || []).length} 步`
    default: return JSON.stringify(p)
  }
}

export default function Scripts() {
  const [items, setItems] = useState([])
  const [templates, setTemplates] = useState([])
  const [devices, setDevices] = useState([])
  const [groups, setGroups] = useState([])
  const [query, setQuery] = useState('')
  // 编辑器状态：null=未打开；{id?, name, steps:[]}
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  // 步骤编辑弹窗
  const [stepModal, setStepModal] = useState(null) // {idx: null|number, ...}
  const [stepForm, setStepForm] = useState({ action: 'open_url', params: {} })

  // 执行弹窗
  const [execModal, setExecModal] = useState(null)
  const [execDev, setExecDev] = useState(new Set())
  const [execResult, setExecResult] = useState(null)
  const [histModal, setHistModal] = useState(null)

  async function load() {
    const [s, t, d] = await Promise.all([
      api.listScripts(),
      api.scriptTemplates(),
      api.listDevices({ page: 1, page_size: 300 }),
    ])
    setItems(s.data)
    setTemplates(t.data)
    setDevices(d.data.items || d.data || [])
  }
  async function loadGroups() {
    try {
      const r = await api.listGroups()
      setGroups(r.data || [])
    } catch (e) { /* 忽略 */ }
  }
  useEffect(() => { load(); loadGroups() }, [])

  const groupMap = Object.fromEntries((groups || []).map((g) => [g.id, g.name]))
  const groupDevices = (gid) => devices.filter((d) => d.group_id === gid)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter((s) =>
      s.name.toLowerCase().includes(q) ||
      JSON.stringify(s.steps).toLowerCase().includes(q))
  }, [items, query])

  // ---- 编辑器 ----
  function startCreate() { setEditing({ name: '', steps: [] }); setMsg(''); setErr('') }
  function startEdit(s) {
    setEditing({ id: s.id, name: s.name, steps: JSON.parse(JSON.stringify(s.steps)) })
    setMsg(''); setErr('')
  }
  function resetEditor() { setEditing(null); setMsg(''); setErr('') }
  function fillTemplate(t) {
    setEditing((cur) => ({ ...(cur || { name: '', steps: [] }), name: t.name, steps: JSON.parse(JSON.stringify(t.steps)) }))
  }
  function openStepModal(idx) {
    if (idx == null) {
      setStepModal({ idx: null })
      setStepForm({ action: 'open_url', params: {} })
    } else {
      const s = editing.steps[idx]
      setStepModal({ idx })
      setStepForm({ action: s.action, params: { ...(s.params || {}) } })
    }
  }
  function stepField(k, v) {
    setStepForm((f) => ({ ...f, params: { ...f.params, [k]: v } }))
  }
  function stepAction(a) { setStepForm({ action: a, params: {} }) }
  function confirmStep() {
    const step = { action: stepForm.action, params: { ...stepForm.params } }
    const steps = [...editing.steps]
    if (stepModal.idx == null) steps.push(step)
    else steps[stepModal.idx] = step
    setEditing({ ...editing, steps })
    setStepModal(null)
  }
  function moveStep(i, dir) {
    const steps = [...editing.steps]
    const j = i + dir
    if (j < 0 || j >= steps.length) return
    const t = steps[i]; steps[i] = steps[j]; steps[j] = t
    setEditing({ ...editing, steps })
  }
  function removeStep(i) {
    setEditing({ ...editing, steps: editing.steps.filter((_, k) => k !== i) })
  }
  async function handleSave(e) {
    e.preventDefault()
    if (!editing || !editing.name.trim()) return setErr('请填写脚本名')
    if (!editing.steps.length) return setErr('请至少添加一个步骤')
    setBusy(true); setErr(''); setMsg('')
    try {
      const body = { name: editing.name.trim(), steps: editing.steps }
      if (editing.id) {
        await api.updateScript(editing.id, body)
        setMsg('脚本更新成功')
      } else {
        const r = await api.createScript(body)
        setMsg(`脚本创建成功（ID ${r.data.id}）`)
      }
      setEditing(null)
      load()
    } catch (e2) {
      setErr(e2.response?.data?.error || '保存失败')
    } finally {
      setBusy(false)
    }
  }

  // ---- 原有操作 ----
  async function handleDelete(id) {
    if (!confirm('确认删除该脚本？')) return
    try {
      await api.deleteScript(id)
      if (editing && editing.id === id) setEditing(null)
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '删除失败')
    }
  }
  async function handleDuplicate(id) {
    setBusy(true)
    try {
      const r = await api.duplicateScript(id)
      setMsg(`已复制为新脚本「${r.data.name}」`)
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '复制失败')
    } finally {
      setBusy(false)
    }
  }
  function openExec(script) {
    setExecDev(new Set())
    setExecModal({ script })
  }
  function toggleDev(id) {
    const next = new Set(execDev)
    next.has(id) ? next.delete(id) : next.add(id)
    setExecDev(next)
  }
  function toggleGroup(gid) {
    const ids = groupDevices(gid).map((d) => d.id)
    if (!ids.length) return
    const next = new Set(execDev)
    const allOn = ids.every((id) => next.has(id))
    ids.forEach((id) => (allOn ? next.delete(id) : next.add(id)))
    setExecDev(next)
  }
  function toggleAllDevices() {
    const next = new Set(execDev)
    const allOn = devices.length > 0 && devices.every((d) => next.has(d.id))
    devices.forEach((d) => (allOn ? next.delete(d.id) : next.add(d.id)))
    setExecDev(next)
  }
  async function handleExecConfirm() {
    const ids = [...execDev]
    if (!ids.length) return setErr('请至少选择一台设备')
    setBusy(true); setErr('')
    try {
      const r = await api.executeScript(execModal.script.id, ids)
      setExecModal(null)
      setExecResult({ script_name: execModal.script.name, ...r.data })
      setMsg(`脚本执行完成：成功 ${r.data.ok} 台${r.data.failed ? `，失败 ${r.data.failed} 台` : ''}`)
    } catch (e) {
      setErr(e.response?.data?.error || '执行失败')
    } finally {
      setBusy(false)
    }
  }
  async function openHistory(script) {
    try {
      const r = await api.scriptExecutions(script.id)
      setHistModal({ script, list: r.data || [] })
    } catch (e) {
      setErr(e.response?.data?.error || '加载历史失败')
    }
  }

  return (
    <div>
      <h2>脚本管理</h2>
      {err && <div className="err">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 430px) 1fr', gap: 16, alignItems: 'start' }}>
        {/* 左侧：脚本列表 */}
        <div className="panel">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <input
              placeholder="搜索脚本名称 / 内容…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ flex: 1 }}
            />
            <button className="accent" onClick={startCreate} disabled={busy}>新建脚本</button>
          </div>
          <div className="device-table-wrap files-table-wrap">
            <table className="device-table">
              <thead>
                <tr><th>名称</th><th>步骤</th><th>操作</th></tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className={editing && editing.id === s.id ? 'row-active' : ''}>
                    <td className="file-name">
                      <span className="file-name-text" title={s.name}>{s.name}</span>
                      <div style={{ fontSize: 11, color: '#94a3b8' }}>{fmtTime(s.created_at)}</div>
                    </td>
                    <td>{s.steps.length}</td>
                    <td className="file-ops">
                      <button className="ghost" onClick={() => openExec(s)} disabled={busy}>执行</button>
                      <button className="ghost" onClick={() => startEdit(s)} disabled={busy}>编辑</button>
                      <button className="ghost" onClick={() => handleDuplicate(s.id)} disabled={busy}>复制</button>
                      <button className="ghost" onClick={() => openHistory(s)}>历史</button>
                      <button className="danger" onClick={() => handleDelete(s.id)} disabled={busy}>删除</button>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="3" className="empty-cell">暂无脚本</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* 右侧：编辑器 */}
        <div className="panel">
          {!editing ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: '#94a3b8' }}>
              <p>点击「新建脚本」开始，或选择左侧脚本进行编辑</p>
            </div>
          ) : (
            <form onSubmit={handleSave}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <h3 style={{ margin: 0 }}>{editing.id ? `编辑脚本 #${editing.id}` : '新建脚本'}</h3>
                {editing.id && <button type="button" className="ghost" onClick={resetEditor}>取消编辑</button>}
              </div>

              <div style={{ marginBottom: 10 }}>
                <div className="hint" style={{ marginBottom: 4 }}>模板（点击填充）</div>
                <div className="dev-pick">
                  {templates.map((t, i) => (
                    <button type="button" key={i} className="chip" onClick={() => fillTemplate(t)}>{t.name}</button>
                  ))}
                  {templates.length === 0 && <span className="hint">暂无模板</span>}
                </div>
              </div>

              <input
                placeholder="脚本名称"
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                style={{ marginBottom: 10 }}
              />

              <div className="hint" style={{ marginBottom: 4 }}>步骤（共 {editing.steps.length} 步）</div>
              {editing.steps.length === 0 && <p className="hint" style={{ margin: '4px 0' }}>尚未添加步骤，点击下方「添加步骤」</p>}
              <div className="script-step-list">
                {editing.steps.map((s, i) => (
                  <div key={i} className="script-step-item">
                    <span className="script-step-idx">{i + 1}</span>
                    <span className="script-step-badge">{ACTIONS[s.action]?.label || s.action}</span>
                    <span className="script-step-summary" title={stepSummary(s)}>{stepSummary(s)}</span>
                    <span className="script-step-ops">
                      <button type="button" className="ghost" onClick={() => moveStep(i, -1)} disabled={i === 0}>↑</button>
                      <button type="button" className="ghost" onClick={() => moveStep(i, 1)} disabled={i === editing.steps.length - 1}>↓</button>
                      <button type="button" className="ghost" onClick={() => openStepModal(i)}>改</button>
                      <button type="button" className="danger" onClick={() => removeStep(i)}>删</button>
                    </span>
                  </div>
                ))}
              </div>
              <button type="button" className="ghost" onClick={() => openStepModal(null)} style={{ margin: '8px 0' }}>＋ 添加步骤</button>

              <div className="modal-actions" style={{ marginTop: 8 }}>
                <button type="submit" className="accent" disabled={busy}>{editing.id ? '保存修改' : '创建脚本'}</button>
              </div>
            </form>
          )}
        </div>
      </div>

      {/* 步骤编辑弹窗 */}
      {stepModal && (
        <div className="modal-mask" onClick={() => setStepModal(null)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>{stepModal.idx == null ? '添加步骤' : `编辑步骤 #${stepModal.idx + 1}`}</span>
              <button className="modal-close" onClick={() => setStepModal(null)}>✕</button>
            </div>
            <div className="hint" style={{ marginBottom: 4 }}>动作类型</div>
            <div className="dev-pick" style={{ marginBottom: 10 }}>
              {ACTION_KEYS.map((a) => (
                <button
                  key={a}
                  type="button"
                  className={`chip ${stepForm.action === a ? 'chip-active' : ''}`}
                  onClick={() => stepAction(a)}
                >
                  {ACTIONS[a].label}
                </button>
              ))}
            </div>
            <div className="hint" style={{ marginBottom: 8 }}>{ACTIONS[stepForm.action].desc}</div>
            {ACTIONS[stepForm.action].fields.map((f) => (
              <div key={f.key} style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 2 }}>{f.label}</label>
                {f.type === 'select' ? (
                  <select value={stepForm.params[f.key] ?? f.def ?? ''} onChange={(e) => stepField(f.key, e.target.value)}>
                    {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    type={f.type}
                    placeholder={f.ph}
                    value={stepForm.params[f.key] ?? (f.def != null ? f.def : '')}
                    onChange={(e) => stepField(f.key, f.type === 'number' ? Number(e.target.value) : e.target.value)}
                  />
                )}
              </div>
            ))}
            <div className="modal-actions">
              <button className="ghost" onClick={() => setStepModal(null)}>取消</button>
              <button onClick={confirmStep}>{stepModal.idx == null ? '添加' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 执行弹窗 */}
      {execModal && (
        <div className="modal-mask" onClick={() => setExecModal(null)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>执行脚本「{execModal.script.name}」</span>
              <button className="modal-close" onClick={() => setExecModal(null)}>✕</button>
            </div>
            <p className="hint">已选 {execDev.size} 台设备，可先按分组/全部快速选择，再单独微调</p>
            <div className="push-sec-title">快速选择</div>
            <div className="dev-pick push-group-pick">
              <label className="chip">
                <input type="checkbox" checked={devices.length > 0 && devices.every((d) => execDev.has(d.id))} onChange={toggleAllDevices} />
                <b>全部设备</b>
                <span className="chip-sub">{devices.length} 台</span>
              </label>
              {groups.map((g) => {
                const ids = groupDevices(g.id).map((d) => d.id)
                const on = ids.length > 0 && ids.every((id) => execDev.has(id))
                return (
                  <label key={g.id} className="chip">
                    <input type="checkbox" checked={on} onChange={() => toggleGroup(g.id)} />
                    <b>{g.name}</b>
                    <span className="chip-sub">{ids.length} 台</span>
                  </label>
                )
              })}
            </div>
            <div className="push-sec-title">单独选择设备</div>
            <div className="dev-pick push-dev-pick">
              {devices.length === 0 && <p className="hint">暂无设备，请先在设备管理创建</p>}
              {devices.map((d) => (
                <label key={d.id} className="chip">
                  <input type="checkbox" checked={execDev.has(d.id)} onChange={() => toggleDev(d.id)} />
                  {d.name}（{d.serial}）
                  <span className="chip-sub">{groupMap[d.group_id] || '未分组'}</span>
                </label>
              ))}
            </div>
            <div className="modal-actions">
              <button className="ghost" onClick={() => setExecModal(null)} disabled={busy}>取消</button>
              <button onClick={handleExecConfirm} disabled={busy}>执行</button>
            </div>
          </div>
        </div>
      )}

      {/* 执行结果明细弹窗 */}
      {execResult && (
        <div className="modal-mask" onClick={() => setExecResult(null)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>执行结果「{execResult.script_name}」</span>
              <button className="modal-close" onClick={() => setExecResult(null)}>✕</button>
            </div>
            <p className="hint">
              成功 <b style={{ color: '#15803d' }}>{execResult.ok}</b> 台 · 失败{' '}
              <b style={{ color: '#b91c1c' }}>{execResult.failed}</b> 台
            </p>
            <div className="exec-result-list">
              {(execResult.results || []).map((r) => (
                <div className={`exec-result-item ${r.ok ? 'ok' : 'fail'}`} key={r.device_id}>
                  <span className="exec-result-name">{r.device_name}（{r.serial || '-'}）</span>
                  <span className="exec-result-msg">{r.message}</span>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={() => setExecResult(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 执行历史弹窗 */}
      {histModal && (
        <div className="modal-mask" onClick={() => setHistModal(null)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>执行历史「{histModal.script.name}」</span>
              <button className="modal-close" onClick={() => setHistModal(null)}>✕</button>
            </div>
            {histModal.list.length === 0 && <p className="hint">暂无执行记录</p>}
            <div className="script-hist-list">
              {histModal.list.map((h) => (
                <div className="script-hist-item" key={h.id}>
                  <div className="script-hist-head">
                    <span className="status-dot" style={{ background: h.status === 'success' ? '#22c55e' : h.status === 'partial' ? '#f59e0b' : '#ef4444' }} />
                    <span className="script-hist-time">{fmtTime(h.created_at)}</span>
                    <span className="script-hist-count">
                      成功 <b style={{ color: '#15803d' }}>{h.ok}</b> / 失败{' '}
                      <b style={{ color: '#b91c1c' }}>{h.failed}</b>
                    </span>
                  </div>
                  <div className="script-hist-detail">
                    {(h.detail || []).map((r) => (
                      <div className={`exec-result-item ${r.ok ? 'ok' : 'fail'}`} key={r.device_id}>
                        <span className="exec-result-name">{r.device_name}（{r.serial || '-'}）</span>
                        <span className="exec-result-msg">{r.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={() => setHistModal(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
