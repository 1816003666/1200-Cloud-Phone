import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

export default function Scripts() {
  const [items, setItems] = useState([])
  const [templates, setTemplates] = useState([])
  const [devices, setDevices] = useState([])
  const [form, setForm] = useState({ name: '', stepsText: '[]' })
  const [selected, setSelected] = useState({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  async function load() {
    const [s, t, d] = await Promise.all([
      api.listScripts(),
      api.scriptTemplates(),
      api.listDevices({ page: 1, page_size: 200 }),
    ])
    setItems(s.data)
    setTemplates(t.data)
    setDevices(d.data.items || d.data || [])
  }
  useEffect(() => { load() }, [])

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
    await api.deleteScript(id)
    load()
  }

  async function handleExecute(id) {
    const ids = selected[id] || []
    if (!ids.length) return setErr('请先勾选要执行的设备')
    setErr('')
    try {
      const r = await api.executeScript(id, ids)
      setMsg(`脚本已在 ${r.data.ok} 台设备上执行（模拟）`)
    } catch (e) {
      setErr(e.response?.data?.error || '执行失败')
    }
  }

  function toggleDevice(sid, devId) {
    const cur = selected[sid] || []
    setSelected({
      ...selected,
      [sid]: cur.includes(devId) ? cur.filter((x) => x !== devId) : [...cur, devId],
    })
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
      <table>
        <thead>
          <tr><th>ID</th><th>名称</th><th>步骤数</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <td>{s.id}</td>
              <td>{s.name}</td>
              <td>{s.steps.length}</td>
              <td>{s.created_at}</td>
              <td>
                <button className="danger" onClick={() => handleDelete(s.id)}>删除</button>
                <button onClick={() => handleExecute(s.id)}>执行</button>
                <div className="dev-pick">
                  {devices.map((d) => (
                    <label key={d.id} className="chip">
                      <input
                        type="checkbox"
                        checked={(selected[s.id] || []).includes(d.id)}
                        onChange={() => toggleDevice(s.id, d.id)}
                      />
                      {d.name}
                    </label>
                  ))}
                </div>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan="5">暂无脚本，先用模板创建一个</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
