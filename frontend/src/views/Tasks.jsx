import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

const ACTIONS = [
  { value: 'health_check', label: '健康巡检' },
  { value: 'open_url', label: '打开网址' },
  { value: 'tap', label: '点击' },
  { value: 'swipe', label: '滑动' },
  { value: 'text', label: '输入文本' },
  { value: 'key', label: '按键' },
  { value: 'install', label: '安装应用' },
  { value: 'sequence', label: '序列' },
  { value: 'wait', label: '等待' },
]

const LEVEL_COLOR = { ok: '#22c55e', warning: '#f59e0b', critical: '#ef4444' }

function fmtTime(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

/* 健康巡检报告渲染 */
function HealthReport({ detail }) {
  const server = detail.server || {}
  const m = server.metrics || {}
  const devs = detail.devices || {}
  const mrow = (label, metric) => (
    <div className="hc-row" key={label}>
      <span>{label}</span>
      <span className="hc-value">
        {metric ? (
          <>
            {label === 'CPU 负载' && `${metric.value} / ${m.cores}核`}
            {label === '内存' && `${metric.used_pct}%（${metric.used_mb}MB/${metric.total_mb}MB）`}
            {label === '磁盘' && `${metric.used_pct}%（${metric.used}/${metric.size}）`}
            {label === '容器' && `${metric.running}/${metric.total}`}
          </>
        ) : '-'}
        <span className="hc-dot" style={{ background: LEVEL_COLOR[metric?.level] || '#94a3b8' }} />
      </span>
    </div>
  )
  return (
    <div className="hc-report">
      <div className="hc-sec">
        <div className="hc-sec-title">
          服务器
          <span className={`hc-badge ${server.ok ? 'ok' : 'fail'}`}>{server.ok ? '正常' : '异常'}</span>
        </div>
        <div className="hc-metrics">
          {mrow('CPU 负载', m.load)}
          {mrow('内存', m.memory)}
          {mrow('磁盘', m.disk)}
          {mrow('容器', m.containers)}
        </div>
        {server.issues?.length > 0 && (
          <div className="hc-issues">
            {server.issues.map((x, i) => <div key={i} className="hc-issue">• {x}</div>)}
          </div>
        )}
        {!server.reachable && <div className="hc-issue">• 服务器不可达（SSH 连接失败）</div>}
      </div>
      <div className="hc-sec">
        <div className="hc-sec-title">
          云手机
          <span className="hc-badge ok">{devs.ok} 正常</span>
          <span className={`hc-badge ${devs.failed ? 'fail' : 'ok'}`}>{devs.failed} 异常</span>
        </div>
        <div className="hc-dev-list">
          {(devs.items || []).map((d) => (
            <div className={`hc-dev ${d.ok ? 'ok' : 'fail'}`} key={d.device_id}>
              <div className="hc-dev-head">
                <span className="hc-dev-name">{d.name}</span>
                <span className="hc-dev-serial">{d.serial}</span>
                <span className={`hc-dot`} style={{ background: d.online ? '#22c55e' : '#ef4444' }} />
                <span className="hc-dev-cpu">CPU {d.cpu ?? '-'}%</span>
                <span className="hc-dev-mem">MEM {d.mem ?? '-'}%</span>
              </div>
              {d.issues?.length > 0 && (
                <div className="hc-issues">{d.issues.map((x, i) => <div key={i} className="hc-issue">• {x}</div>)}</div>
              )}
            </div>
          ))}
          {devs.items?.length === 0 && <div className="hint">无云手机设备</div>}
        </div>
      </div>
    </div>
  )
}

export default function Tasks() {
  const [list, setList] = useState([])
  const [form, setForm] = useState({
    name: '', action: 'health_check', schedule_type: 'interval', interval_seconds: 86400, cron_expr: '',
  })
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [hist, setHist] = useState(null) // {task, list}

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
    setErr(''); setMsg('')
    if (form.action === 'health_check') {
      const n = prompt('健康巡检默认巡检全部云手机。如需只巡检部分，请稍后在设备管理选择设备；确认创建？')
      if (n === null) return
    }
    try {
      await api.createTask({
        ...form,
        params: {}, device_ids: [],
        interval_seconds: Number(form.interval_seconds),
        cron_expr: form.cron_expr || '',
      })
      setMsg('任务已创建' + (form.action === 'health_check' ? '，可点「立即执行」先跑一次巡检' : ''))
      setForm({ ...form, name: '', cron_expr: '' })
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleRun(id) {
    try {
      await api.runTask(id)
      setMsg('已触发执行，可在「历史」查看结果')
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '执行失败')
    }
  }
  async function handleDelete(id) {
    if (!confirm('确认删除任务？')) return
    await api.deleteTask(id)
    load()
  }
  async function openHistory(t) {
    try {
      const r = await api.taskExecutions(t.id)
      setHist({ task: t, list: r.data || [] })
    } catch (e) {
      setErr(e.response?.data?.error || '加载历史失败')
    }
  }

  const actionLabel = (a) => ACTIONS.find((x) => x.value === a)?.label || a

  return (
    <div>
      <h2>任务调度</h2>
      {err && <div className="err">{err}</div>}
      {msg && <div className="ok">{msg}</div>}
      <form onSubmit={handleSubmit} className="task-form">
        <input placeholder="任务名（如：每日健康巡检）" value={form.name} onChange={(e) => update('name', e.target.value)} />
        <select value={form.action} onChange={(e) => update('action', e.target.value)}>
          {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
        <select value={form.schedule_type} onChange={(e) => update('schedule_type', e.target.value)}>
          <option value="once">单次</option>
          <option value="interval">周期</option>
          <option value="cron">Cron</option>
        </select>
        {form.schedule_type === 'interval' && (
          <select value={form.interval_seconds} onChange={(e) => update('interval_seconds', Number(e.target.value))}>
            <option value={3600}>每 1 小时</option>
            <option value={21600}>每 6 小时</option>
            <option value={43200}>每 12 小时</option>
            <option value={86400}>每天</option>
            <option value={604800}>每周</option>
          </select>
        )}
        {form.schedule_type === 'cron' && (
          <input
            placeholder="cron 表达式，如 0 2 * * *"
            value={form.cron_expr || ''}
            onChange={(e) => update('cron_expr', e.target.value)}
            style={{ width: 190 }}
          />
        )}
        <button type="submit">创建任务</button>
      </form>

      <div className="device-table-wrap files-table-wrap">
        <table className="device-table">
          <thead>
            <tr><th>ID</th><th>名称</th><th>动作</th><th>类型</th><th>下次执行</th><th>操作</th></tr>
          </thead>
          <tbody>
            {list.map((t) => (
              <tr key={t.id}>
                <td>{t.id}</td>
                <td className="file-name"><span className="file-name-text" title={t.name}>{t.name}</span></td>
                <td>{actionLabel(t.action)}</td>
                <td>{t.schedule_type === 'once' ? '单次' : t.schedule_type === 'cron' ? `Cron: ${t.cron_expr || ''}` : '周期'}</td>
                <td>{fmtTime(t.next_run)}</td>
                <td className="file-ops">
                  <button className="accent" onClick={() => handleRun(t.id)}>立即执行</button>
                  <button className="ghost" onClick={() => openHistory(t)}>历史</button>
                  <button className="danger" onClick={() => handleDelete(t.id)}>删除</button>
                </td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr><td colSpan="6" className="empty-cell">暂无任务，建议创建一个「每日健康巡检」周期任务</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 执行历史弹窗 */}
      {hist && (
        <div className="modal-mask" onClick={() => setHist(null)}>
          <div className="modal-body modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>执行历史「{hist.task.name}」</span>
              <button className="modal-close" onClick={() => setHist(null)}>✕</button>
            </div>
            {hist.list.length === 0 && <p className="hint">暂无执行记录，点「立即执行」跑一次</p>}
            <div className="script-hist-list">
              {hist.list.map((h) => (
                <div className="script-hist-item" key={h.id}>
                  <div className="script-hist-head">
                    <span className={`status-dot`} style={{ background: h.status === 'success' ? '#22c55e' : '#ef4444' }} />
                    <span className="script-hist-time">{fmtTime(h.finished_at)}</span>
                    {h.detail?.summary && <span className="script-hist-summary">{h.detail.summary}</span>}
                  </div>
                  {h.detail?.type === 'health_check' ? (
                    <HealthReport detail={h.detail} />
                  ) : (
                    <p className="hint">完成 {h.ok}/{h.total} 台，失败 {h.failed} 台</p>
                  )}
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={() => setHist(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
