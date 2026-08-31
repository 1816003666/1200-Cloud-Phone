import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

const FIELDS = [
  { key: 'alert_offline_seconds', label: '离线判定秒数', desc: '运行中设备超过该秒数无心跳即判定离线（默认 120s）', unit: '秒' },
  { key: 'alert_cpu_limit', label: '云手机 CPU 阈值', desc: 'CPU 使用率超过该值触发资源告警（默认 90%）', unit: '%' },
  { key: 'alert_mem_limit', label: '云手机内存阈值', desc: '内存使用率超过该值触发资源告警（默认 90%）', unit: '%' },
  { key: 'alert_webhook_url', label: '告警通知 Webhook', desc: '产生告警时推送该地址（支持飞书/企业微信机器人或自建接口），留空则不通知' },
]

export default function Settings() {
  const [form, setForm] = useState({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  async function load() {
    try {
      const r = await api.getSettings()
      setForm(r.data)
    } catch (e) {
      setErr(e.response?.data?.error || '加载失败')
    }
  }
  useEffect(() => { load() }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true); setErr(''); setMsg('')
    try {
      const payload = {}
      for (const f of FIELDS) {
        if (f.key === 'alert_webhook_url') payload[f.key] = (form[f.key] || '').trim()
        else payload[f.key] = Number(form[f.key] || 0)
      }
      await api.updateSettings(payload)
      setMsg('设置已保存，调度器将自动按新阈值生效')
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <h2>系统设置</h2>
      {err && <div className="err">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <form onSubmit={handleSave} className="settings-form">
        <div className="settings-section">
          <div className="settings-section-title">告警与巡检阈值</div>
          {FIELDS.map((f) => (
            <div className="settings-row" key={f.key}>
              <label className="settings-label">
                <span>{f.label}</span>
                {f.unit && <em>{f.unit}</em>}
              </label>
              <input
                type={f.key === 'alert_webhook_url' ? 'text' : 'number'}
                className={f.key === 'alert_webhook_url' ? 'settings-webhook' : 'settings-input'}
                placeholder={f.key === 'alert_webhook_url' ? 'https://...' : ''}
                value={form[f.key] ?? ''}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              />
              <p className="settings-desc">{f.desc}</p>
            </div>
          ))}
        </div>

        <div className="settings-actions">
          <button type="submit" disabled={saving}>{saving ? '保存中…' : '保存设置'}</button>
        </div>
      </form>
    </div>
  )
}
