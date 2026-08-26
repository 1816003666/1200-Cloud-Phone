import { useEffect, useState } from 'react'
import { api } from '../api/client.js'
import { useAuth } from '../store/auth.jsx'

const ROLES = ['viewer', 'operator', 'admin', 'superadmin']

export default function Users() {
  const { user } = useAuth()
  const isSuper = user?.role === 'superadmin'
  const [list, setList] = useState([])
  const [form, setForm] = useState({ username: '', password: '', role: 'viewer' })
  const [err, setErr] = useState('')

  async function load() {
    const r = await api.listUsers()
    setList(r.data)
  }
  useEffect(() => { load() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    try {
      await api.createUser(form)
      setForm({ username: '', password: '', role: 'viewer' })
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleRole(u) {
    const role = prompt(`修改 ${u.username} 的角色 (viewer/operator/admin/superadmin):`, u.role)
    if (!role || !ROLES.includes(role)) return
    await api.updateUser(u.id, { role })
    load()
  }
  async function handleDelete(id) {
    if (!confirm('确认删除用户？')) return
    await api.deleteUser(id)
    load()
  }

  return (
    <div>
      <h2>用户管理（admin 及以上）</h2>
      {err && <div className="err">{err}</div>}
      <form onSubmit={handleSubmit} className="task-form">
        <input placeholder="用户名" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input type="password" placeholder="密码" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {/* admin 不能创建 admin 及以上；superadmin 才能选 admin/superadmin */}
          {ROLES.filter((r) => isSuper || r === 'viewer' || r === 'operator').map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <button type="submit">新建用户</button>
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          {list.map((u) => (
            <tr key={u.id}>
              <td>{u.id}</td>
              <td>{u.username}</td>
              <td>{u.role}</td>
              <td>{u.is_active ? '启用' : '停用'}</td>
              <td>
                <button onClick={() => handleRole(u)}>改角色</button>
                <button className="danger" onClick={() => handleDelete(u.id)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
