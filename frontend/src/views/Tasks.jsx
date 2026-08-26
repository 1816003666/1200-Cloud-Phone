import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

const ACTIONS = ['open_url', 'tap', 'swipe', 'text', 'key', 'install', 'sequence', 'wait']

export default function Tasks() {
  const [list, setList] = useState([])
  const [form, setForm] = useState({
    name: '', action: 'open_url', schedule_type: 'once', interval_seconds: 3600,
  })
  const [err, setErr] = useState('')

  async function load() {
    const r = await api.listTasks()
    setList(r.data)
  }
  useEffect(() => { load() }, [])

  function update(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    try {
      await api.createTask({
        ...form,
        params: {}, device_ids: [],
        interval_seconds: Number(form.interval_seconds),
      })
      setForm({ name: '', action: 'open_url', schedule_type: 'once', interval_seconds: 3600 })
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleRun(id) {
    await api.runTask(id)
    alert('已触发执行')
    load()
  }
  async function handleDelete(id) {
    if (!confirm('确认删除任务？')) return
    await api.deleteTask(id)
    load()
  }

  return (
    <div>
      <h2>任务调度</h2>
      {err && <div className="err">{err}</div>}
      <form onSubmit={handleSubmit} className="task-form">
        <input placeholder="任务名" value={form.name} onChange={(e) => update('name', e.target.value)} />
        <select value={form.action} onChange={(e) => update('action', e.target.value)}>
          {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={form.schedule_type} onChange={(e) => update('schedule_type', e.target.value)}>
          <option value="once">单次</option>
          <option value="interval">周期</option>
        </select>
        {form.schedule_type === 'interval' && (
          <input
            type="number" min="1" value={form.interval_seconds}
            onChange={(e) => update('interval_seconds', e.target.value)}
            style={{ width: 100 }} placeholder="间隔(秒)"
          />
        )}
        <button type="submit">创建任务</button>
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>名称</th><th>动作</th><th>类型</th><th>下次执行</th><th>操作</th></tr>
        </thead>
        <tbody>
          {list.map((t) => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>{t.name}</td>
              <td>{t.action}</td>
              <td>{t.schedule_type}</td>
              <td>{t.next_run || '-'}</td>
              <td>
                <button onClick={() => handleRun(t.id)}>立即执行</button>
                <button className="danger" onClick={() => handleDelete(t.id)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
