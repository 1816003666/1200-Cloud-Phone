import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client.js'

export default function Files() {
  const [items, setItems] = useState([])
  const [devices, setDevices] = useState([])
  const [selected, setSelected] = useState({})      // 文件id -> [deviceId...]
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const fileRef = useRef(null)

  async function load() {
    const r = await api.listFiles({ page: 1, page_size: 100 })
    setItems(r.data.items)
  }
  async function loadDevices() {
    const r = await api.listDevices({ page: 1, page_size: 200 })
    setDevices(r.data.items || r.data || [])
  }
  useEffect(() => { load(); loadDevices() }, [])

  async function handleUpload(e) {
    e.preventDefault()
    setErr(''); setMsg('')
    const file = fileRef.current?.files?.[0]
    if (!file) return setErr('请选择文件')
    try {
      await api.uploadFile(file)
      setMsg('上传成功')
      fileRef.current.value = ''
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '上传失败')
    }
  }

  async function handleDelete(id) {
    if (!confirm('确认删除该文件？')) return
    await api.deleteFile(id)
    load()
  }

  async function handlePush(id) {
    const ids = selected[id] || []
    if (!ids.length) return setErr('请先勾选要推送的设备')
    setErr('')
    try {
      const r = await api.pushFile(id, ids)
      setMsg(`已推送至 ${r.data.ok} 台设备`)
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '推送失败')
    }
  }

  function toggleDevice(fileId, devId) {
    const cur = selected[fileId] || []
    setSelected({
      ...selected,
      [fileId]: cur.includes(devId) ? cur.filter((x) => x !== devId) : [...cur, devId],
    })
  }

  return (
    <div>
      <h2>文件管理</h2>
      {err && <div className="err">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <form onSubmit={handleUpload} className="task-form">
        <input type="file" ref={fileRef} />
        <button type="submit">上传文件</button>
      </form>

      <p className="hint">设备清单（用于“推送到设备”）：{devices.length} 台</p>
      <table>
        <thead>
          <tr><th>ID</th><th>文件名</th><th>大小</th><th>上传时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr key={f.id}>
              <td>{f.id}</td>
              <td>{f.filename}</td>
              <td>{(f.size / 1024).toFixed(1)} KB</td>
              <td>{f.created_at}</td>
              <td>
                <button onClick={() => api.downloadFile(f.id, f.filename)}>下载</button>
                <button className="danger" onClick={() => handleDelete(f.id)}>删除</button>
                <button onClick={() => handlePush(f.id)}>推送到设备</button>
                <div className="dev-pick">
                  {devices.map((d) => (
                    <label key={d.id} className="chip">
                      <input
                        type="checkbox"
                        checked={(selected[f.id] || []).includes(d.id)}
                        onChange={() => toggleDevice(f.id, d.id)}
                      />
                      {d.name}
                    </label>
                  ))}
                </div>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan="5">暂无文件，先上传一个</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
