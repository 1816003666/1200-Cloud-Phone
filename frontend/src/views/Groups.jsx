import { useEffect, useState } from 'react'
import { api } from '../api/client.js'
import { useAuth } from '../store/auth.jsx'

export default function Groups() {
  const { user } = useAuth()
  const isAdmin = ['admin', 'superadmin'].includes(user?.role)
  const [items, setItems] = useState([])
  const [form, setForm] = useState({ name: '', description: '' })
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  async function load() {
    const r = await api.listGroups()
    setItems(r.data)
  }
  useEffect(() => { load() }, [])

  async function handleCreate(e) {
    e.preventDefault()
    setErr(''); setMsg('')
    try {
      await api.createGroup(form)
      setForm({ name: '', description: '' })
      setMsg('分组创建成功')
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleDelete(id) {
    if (!confirm('确认删除该分组？组内设备会变为未分组')) return
    await api.deleteGroup(id)
    load()
  }

  async function handleBatch(id, action) {
    if (!confirm(`确认对分组执行「${action}」？(模拟)`)) return
    try {
      const r = await api.groupBatchAction(id, { action })
      setMsg(`已对 ${r.data.ok} 台设备执行 ${action}`)
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '操作失败')
    }
  }

  return (
    <div>
      <h2>分组管理</h2>
      {err && <div className="err">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      {isAdmin && (
        <form onSubmit={handleCreate} className="task-form">
          <input placeholder="分组名" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="描述" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <button type="submit">新建分组</button>
        </form>
      )}

      <table>
        <thead>
          <tr><th>ID</th><th>名称</th><th>设备数</th><th>描述</th><th>操作</th></tr>
        </thead>
        <tbody>
          {items.map((g) => (
            <tr key={g.id}>
              <td>{g.id}</td>
              <td>{g.name}</td>
              <td>{g.device_count}</td>
              <td>{g.description}</td>
              <td>
                <button onClick={() => handleBatch(g.id, 'start')}>批量开机</button>
                <button onClick={() => handleBatch(g.id, 'stop')}>批量关机</button>
                <button onClick={() => handleBatch(g.id, 'destroy')}>批量销毁</button>
                {isAdmin && <button className="danger" onClick={() => handleDelete(g.id)}>删除</button>}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan="5">暂无分组</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
