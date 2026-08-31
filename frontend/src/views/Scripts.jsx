import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

function fmtTime(s) {
  if (!s) return '-'
  const d = new Date(s)
  return d.toLocaleString('zh-CN', { hour12: false })
}

export default function Scripts() {
  const [items, setItems] = useState([])
  const [templates, setTemplates] = useState([])
  const [devices, setDevices] = useState([])
  const [groups, setGroups] = useState([])
  const [form, setForm] = useState({ name: '', stepsText: '[]' })
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  // 执行弹窗
  const [execModal, setExecModal] = useState(null)   // {script, ids?}
  const [execDev, setExecDev] = useState(new Set())
  // 执行结果明细
  const [execResult, setExecResult] = useState(null)
  // 历史弹窗
  const [histModal, setHistModal] = useState(null)   // {script, list}

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

  async function handleCreate(e) {
    e.preventDefault()
    setErr(''); setMsg('')
    try {
      JSON.parse(form.stepsText) // 校验 JSON
    } catch {
      return setErr('步骤必须是合法 JSON 数组')
    }
    try {
      await api.createScript({ name: form.name, steps: JSON.parse(form.stepsText) })
      setForm({ name: '', stepsText: '[]' })
      setMsg('脚本创建成功')
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleDelete(id) {
    if (!confirm('确认删除该脚本？')) return
    try {
      await api.deleteScript(id)
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

  function fillTemplate(t) {
    setForm({ name: t.name, stepsText: JSON.stringify(t.steps, null, 2) })
  }

  return (
    <div>
      <h2>脚本管理</h2>
      {err && <div className="err">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <h3>模板</h3>
      <div className="dev-pick">
        {templates.map((t, i) => (
          <button key={i} className="chip" onClick={() => fillTemplate(t)}>{t.name}</button>
        ))}
      </div>

      <h3>新建脚本</h3>
      <form onSubmit={handleCreate} className="task-form">
        <input placeholder="脚本名" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <textarea
          rows={4}
          placeholder='步骤 JSON，例如 [{"action":"open_url","params":{"url":"https://x.com"}}]'
          value={form.stepsText}
          onChange={(e) => setForm({ ...form, stepsText: e.target.value })}
        />
        <button type="submit">创建</button>
      </form>

      <h3>脚本列表</h3>
      <div className="device-table-wrap files-table-wrap">
        <table className="device-table">
          <thead>
            <tr><th>ID</th><th>名称</th><th>步骤数</th><th>创建时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td className="file-name"><span className="file-name-text" title={s.name}>{s.name}</span></td>
                <td>{s.steps.length}</td>
                <td>{fmtTime(s.created_at)}</td>
                <td className="file-ops">
                  <button className="accent" onClick={() => openExec(s)} disabled={busy}>执行</button>
                  <button className="ghost" onClick={() => handleDuplicate(s.id)} disabled={busy}>复制</button>
                  <button className="ghost" onClick={() => openHistory(s)}>历史</button>
                  <button className="danger" onClick={() => handleDelete(s.id)} disabled={busy}>删除</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan="5" className="empty-cell">暂无脚本，先用模板创建一个</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 执行弹窗：按分组 / 全部 / 单独选设备 */}
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
                <input
                  type="checkbox"
                  checked={devices.length > 0 && devices.every((d) => execDev.has(d.id))}
                  onChange={toggleAllDevices}
                />
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
                    <span className={`status-dot`} style={{ background: h.status === 'success' ? '#22c55e' : h.status === 'partial' ? '#f59e0b' : '#ef4444' }} />
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
