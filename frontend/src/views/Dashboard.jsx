import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [server, setServer] = useState(null)

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

  // 服务器实时监控（SSH 采集开销较大，15 秒轮询）
  useEffect(() => {
    let alive = true
    const load = () => api.serverMetrics().then((r) => alive && setServer(r.data))
    load()
    const t = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  // 历史趋势图
  const [trend, setTrend] = useState([])
  const [trendHours, setTrendHours] = useState(24)
  useEffect(() => {
    let alive = true
    const load = () => api.metricsTrend(trendHours).then((r) => alive && setTrend(r.data))
    load()
    const t = setInterval(load, 30000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [trendHours])

  if (!data) return <div className="loading">加载看板…</div>
  const { kpis, status_distribution, group_distribution, recent_devices, last_execution } = data

  return (
    <div>
      <h2>数据看板</h2>
      <div className="kpi-row">
        <Kpi label="设备总数" value={kpis.total_devices} icon="M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm4 4v10M12 7v10M16 7v10" tone="teal" />
        <Kpi label="运行中" value={kpis.running} icon="M8 5v14l11-7z" tone="green" />
        <Kpi label="异常" value={kpis.error} icon="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" tone="red" />
        <Kpi label="分组数" value={kpis.groups} icon="M3 7h18M6 12h12M10 17h4" tone="blue" />
        <Kpi label="任务数" value={kpis.tasks} icon="M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" tone="amber" />
        <Kpi label="启用任务" value={kpis.enabled_tasks} icon="M22 11.1V12a10 10 0 1 1-5.93-9.14M22 4L12 14.01l-3-3" tone="violet" />
      </div>

      <ServerPanel server={server} />

      <TrendPanel data={trend} hours={trendHours} onHours={setTrendHours} />

      <div className="grid-2">
        <Panel title="设备状态分布">
          <Bar data={Object.fromEntries(Object.entries(status_distribution).map(([k, v]) => [STATUS_CN[k] || k, v]))} />
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
                <td className="cell-id">{d.id}</td>
                <td>{d.name}</td>
                <td><span className={`badge st-${d.status}`}>{d.status === 'running' ? '运行中' : d.status === 'error' ? '异常' : d.status === 'offline' ? '离线' : d.status}</span></td>
                <td className="cell-mono">{d.ip}</td>
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

const KPI_TONES = {
  teal: { bg: '#ccfbf1', fg: '#0f766e' },
  green: { bg: '#dcfce7', fg: '#15803d' },
  red: { bg: '#fee2e2', fg: '#b91c1c' },
  blue: { bg: '#dbeafe', fg: '#1d4ed8' },
  amber: { bg: '#fef3c7', fg: '#b45309' },
  violet: { bg: '#ede9fe', fg: '#6d28d9' },
}

const LEVEL_COLOR = { ok: '#22c55e', warning: '#f59e0b', critical: '#ef4444' }
const LEVEL_BAR = { ok: 'linear-gradient(90deg,#22c55e,#4ade80)', warning: 'linear-gradient(90deg,#f59e0b,#fbbf24)', critical: 'linear-gradient(90deg,#ef4444,#f87171)' }

const STATUS_CN = { running: '运行中', error: '异常', stopped: '已停止', creating: '创建中' }

/* 服务器实时状态面板 */
function ServerPanel({ server }) {
  if (!server) return <Panel title="服务器实时状态"><div className="loading" style={{ padding: 8 }}>采集服务器数据…</div></Panel>
  const s = server.server || {}
  const m = s.metrics || {}
  const dev = server.devices || {}

  const Metric = ({ label, value, sub, pct, level, unit }) => (
    <div className="srv-metric">
      <div className="srv-metric-top">
        <span className="srv-metric-label">{label}</span>
        <span className="srv-metric-dot" style={{ background: LEVEL_COLOR[level] || '#94a3b8' }} />
      </div>
      <div className="srv-metric-value">
        {value}
        {unit && <span className="srv-metric-unit">{unit}</span>}
      </div>
      <div className="srv-metric-sub">{sub}</div>
      {pct != null && (
        <div className="srv-bar-track">
          <div className="srv-bar-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: LEVEL_BAR[level] || LEVEL_BAR.ok }} />
        </div>
      )}
    </div>
  )

  const memPct = m.memory?.used_pct ?? 0
  const diskPct = m.disk?.used_pct ?? 0
  const loadPct = m.load?.ratio != null ? Math.min(100, Math.round(m.load.ratio * 100)) : 0

  return (
    <Panel title={`服务器实时状态 · ${s.host || '-'}`}>
      {!s.reachable ? (
        <div className="srv-error">服务器不可达（SSH 连接失败），无法采集实时数据</div>
      ) : (
        <div className="srv-grid">
          <Metric label="CPU 负载" value={m.load?.value ?? '-'} sub={`${m.load?.ratio ?? '-'} × ${m.cores} 核`} pct={loadPct} level={m.load?.level} />
          <Metric label="内存" value={m.memory?.used_pct ?? '-'} sub={`${m.memory?.used_mb ?? '-'}MB / ${m.memory?.total_mb ?? '-'}MB`} pct={memPct} level={m.memory?.level} unit="%" />
          <Metric label="磁盘" value={diskPct ?? '-'} sub={`${m.disk?.used ?? '-'} / ${m.disk?.size ?? '-'}`} pct={diskPct} level={m.disk?.level} unit="%" />
          <Metric label="Docker 容器" value={`${m.containers?.running ?? '-'}/${m.containers?.total ?? '-'}`} sub="运行 / 总数" pct={m.containers?.total ? Math.round(m.containers.running / m.containers.total * 100) : 0} level={m.containers?.level} />
          <Metric label="云手机在线" value={`${dev.online ?? '-'}/${dev.total ?? '-'}`} sub={`运行 ${dev.running ?? '-'} · 异常 ${dev.error ?? '-'}`} pct={dev.total ? Math.round((dev.online ?? 0) / dev.total * 100) : 0} level={dev.error ? 'warning' : 'ok'} />
        </div>
      )}
      {server.collected_at && <div className="srv-updated">更新于 {new Date(server.collected_at).toLocaleTimeString('zh-CN', { hour12: false })}</div>}
    </Panel>
  )
}

function Kpi({ label, value, icon, tone = 'teal' }) {
  const t = KPI_TONES[tone] || KPI_TONES.teal
  return (
    <div className="kpi">
      <div className="kpi-icon" style={{ background: t.bg, color: t.fg }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d={icon} />
        </svg>
      </div>
      <div className="kpi-body">
        <div className="kpi-value">{value}</div>
        <div className="kpi-label">{label}</div>
      </div>
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

/* 历史趋势折线图（纯 SVG 自绘，无需图表库） */
function TrendPanel({ data, hours, onHours }) {
  const chart = (title, key, color, max = 100, fmt = (v) => `${v ?? '-'}%`) => {
    const pts = data.map((d) => d[key]).filter((v) => v != null)
    const W = 460, H = 120, pad = 6
    const maxv = Math.max(max, ...pts.map((v) => Math.max(0, v)), 1)
    const x = (i) => pad + (data.length <= 1 ? 0 : (i / (data.length - 1)) * (W - pad * 2))
    const y = (v) => H - pad - (Math.max(0, Math.min(maxv, v)) / maxv) * (H - pad * 2)
    const line = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(d[key] ?? 0).toFixed(1)}`).join(' ')
    const last = pts[pts.length - 1]
    return (
      <div className="trend-chart">
        <div className="trend-head">
          <span className="trend-title">{title}</span>
          <span className="trend-last" style={{ color }}>{fmt(last)}</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="trend-svg">
          <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="#e2e8f0" strokeWidth="1" />
          <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    )
  }
  const online = data[data.length - 1]
  return (
    <Panel title={`历史趋势 · 最近 ${hours} 小时`}>
      {data.length === 0 ? (
        <div className="hint">数据采集中…（每 60 秒一个采样点，稍后刷新）</div>
      ) : (
        <>
          <div className="trend-ops">
            {[24, 72, 168].map((h) => (
              <button key={h} className={`chip ${hours === h ? 'active' : ''}`} onClick={() => onHours(h)}>{h === 24 ? '24 小时' : h === 72 ? '3 天' : '7 天'}</button>
            ))}
          </div>
          <div className="trend-grid">
            {chart('服务器内存', 'server_mem', '#3b82f6')}
            {chart('服务器磁盘', 'server_disk', '#f59e0b')}
            {chart('CPU 负载(×100)', 'server_cpu', '#10b981')}
            <div className="trend-chart">
              <div className="trend-head">
                <span className="trend-title">设备在线</span>
                <span className="trend-last" style={{ color: '#8b5cf6' }}>{online?.devices_online ?? '-'}/{online?.devices_total ?? '-'}</span>
              </div>
              <svg viewBox="0 0 460 120" preserveAspectRatio="none" className="trend-svg">
                <line x1="6" y1="114" x2="454" y2="114" stroke="#e2e8f0" strokeWidth="1" />
                {(() => {
                  const pts = data.map((d) => d.devices_online).filter((v) => v != null)
                  const tot = Math.max(...data.map((d) => d.devices_total || 1))
                  const W2 = 460, H2 = 120, pad2 = 6
                  const x2 = (i) => pad2 + (data.length <= 1 ? 0 : (i / (data.length - 1)) * (W2 - pad2 * 2))
                  const y2 = (v) => H2 - pad2 - (Math.min(tot, Math.max(0, v || 0)) / tot) * (H2 - pad2 * 2)
                  const line2 = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${x2(i).toFixed(1)},${y2(d.devices_online ?? 0).toFixed(1)}`).join(' ')
                  return <path d={line2} fill="none" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                })()}
              </svg>
            </div>
          </div>
        </>
      )}
    </Panel>
  )
}
