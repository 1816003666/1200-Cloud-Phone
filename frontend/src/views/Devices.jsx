import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

export default function Devices() {
  const [list, setList] = useState([])
  const [name, setName] = useState('')
  const [count, setCount] = useState(5)
  const [err, setErr] = useState('')

  async function load() {
    const r = await api.listDevices()
    setList(r.data)
  }
  useEffect(() => { load() }, [])

  async function handleCreate(e) {
    e.preventDefault()
    setErr('')
    try {
      await api.createDevice({ name, backend: 'simulator' })
      setName('')
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleBatch(e) {
    e.preventDefault()
    setErr('')
    try {
      await api.batchCreate({ count: Number(count), prefix: 'phone', backend: 'simulator' })
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '批量创建失败')
    }
  }

  async function handleDelete(id) {
    if (!confirm('确认删除该设备？')) return
    await api.deleteDevice(id)
    load()
  }

  async function handleControl(id, action) {
    await api.controlDevice(id, action, {})
    alert(`${action} 已下发`)
  }

  return (
    <div>
      <h2>设备管理</h2>
      {err && <div className="err">{err}</div>}
      <div className="toolbar">
        <form onSubmit={handleCreate} className="inline">
          <input placeholder="设备名" value={name} onChange={(e) => setName(e.target.value)} />
          <button type="submit">创建 1 台</button>
        </form>
        <form onSubmit={handleBatch} className="inline">
          <input
            type="number" min="1" max="200" value={count}
            onChange={(e) => setCount(e.target.value)}
            style={{ width: 80 }}
          />
          <button type="submit">批量创建</button>
        </form>
      </div>

      <table>
        <thead>
          <tr><th>ID</th><th>名称</th><th>状态</th><th>后端</th><th>出口IP</th><th>操作</th></tr>
        </thead>
        <tbody>
          {list.map((d) => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>{d.name}</td>
              <td>{d.status}</td>
              <td>{d.backend}</td>
              <td>{d.ip}</td>
              <td>
                <button onClick={() => handleControl(d.id, 'tap')}>点按</button>
                <button onClick={() => handleControl(d.id, 'text')}>输入</button>
                <button className="danger" onClick={() => handleDelete(d.id)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
