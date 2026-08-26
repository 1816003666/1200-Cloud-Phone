import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

export default function Dashboard() {
  const [data, setData] = useState(null)

  useEffect(() => {
    let alive = true
    const load = () => api.overview().then((r) => alive && setData(r.data))
    load()
    const t = setInterval(load, 5000) // 每 5 秒轮询刷新
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  if (!data) return <div className="loading">加载看板…</div>
  const { kpis, status_distribution, group_distribution, recent_devices, last_execution } = data

  return (
    <div>
      <h2>数据看板</h2>
      <div className="kpi-row">
        <Kpi label="设备总数" value={kpis.total_devices} />
        <Kpi label="运行中" value={kpis.running} />
        <Kpi label="异常" value={kpis.error} />
        <Kpi label="分组数" value={kpis.groups} />
        <Kpi label="任务数" value={kpis.tasks} />
        <Kpi label="启用任务" value={kpis.enabled_tasks} />
      </div>

      <div className="grid-2">
        <Panel title="设备状态分布">
          <Bar data={status_distribution} />
        </Panel>
        <Panel title="分组设备分布">
          <Bar data={Object.fromEntries(group_distribution.map((g) => [g.group, g.count]))} />
        </Panel>
      </div>

      <Panel title="最近设备">
        <table>
          <thead>
            <tr><th>ID</th><th>名称</th><th>状态</th><th>出口 IP</th></tr>
          </thead>
          <tbody>
            {recent_devices.map((d) => (
              <tr key={d.id}>
                <td>{d.id}</td><td>{d.name}</td><td>{d.status}</td><td>{d.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {last_execution && (
        <p className="hint">
          最近一次任务执行：#{last_execution.id} 成功 {last_execution.ok} / 失败 {last_execution.failed}
        </p>
      )}
    </div>
  )
}

function Kpi({ label, value }) {
  return (
    <div className="kpi">
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

function Panel({ title, children }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      {children}
    </div>
  )
}

function Bar({ data }) {
  const max = Math.max(1, ...Object.values(data))
  return (
    <div className="bars">
      {Object.entries(data).map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span className="bar-key">{k}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} />
          </div>
          <span className="bar-val">{v}</span>
        </div>
      ))}
    </div>
  )
}
