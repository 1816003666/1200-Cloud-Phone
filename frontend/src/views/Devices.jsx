import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client.js'

/* ---------- 云手机屏幕预览（小卡片截图 / 大屏 MSE 视频流） ---------- */
function PhoneScreen({ device, large }) {
  const [now, setNow] = useState(new Date())
  const [screenshot, setScreenshot] = useState(null)
  const [ssError, setSsError] = useState(false)
  const [streamStatus, setStreamStatus] = useState('connecting')
  const isRedroid = device.backend === 'redroid'
  const isError = device.status === 'error'
  const isStopped = device.status === 'stopped'

  // 时钟（simulator 用）
  useEffect(() => {
    if (isRedroid) return
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [isRedroid])

  // 小卡片：截图轮询（每 3 秒）
  useEffect(() => {
    if (!isRedroid || isError || isStopped || large) return
    let cancelled = false
    let retryCount = 0
    async function fetchSS() {
      try {
        const r = await api.deviceScreenshot(device.id)
        if (cancelled) return
        if (r.data && r.data.size > 0) {
          const url = URL.createObjectURL(r.data)
          setScreenshot((old) => { if (old) URL.revokeObjectURL(old); return url })
          setSsError(false)
          retryCount = 0
        } else {
          throw new Error('empty screenshot')
        }
      } catch (e) {
        if (cancelled) return
        retryCount++
        if (retryCount >= 3) setSsError(true)
      }
    }
    fetchSS()
    const t = setInterval(fetchSS, 3000)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [device.id, isRedroid, isError, isStopped, large])

  // 大屏预览：ws-scrcpy iframe（内部 MSE 播放 H.264）
  const WS_SCRCPY_HOST = '192.168.9.131'
  const WS_SCRCPY_PORT = 8100

  function buildScrcpyUrl() {
    if (!device.serial) return ''
    const port = device.serial.split(':').pop()
    const udid = `127.0.0.1:${port}`
    const wsUrl = `ws://${WS_SCRCPY_HOST}:${WS_SCRCPY_PORT}/?action=proxy-adb&remote=tcp:8886&udid=${encodeURIComponent(udid)}`
    return `http://${WS_SCRCPY_HOST}:${WS_SCRCPY_PORT}/#!action=stream&udid=${encodeURIComponent(udid)}&player=mse&ws=${encodeURIComponent(wsUrl)}`
  }

  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const apps = ['微信', '抖音', '淘宝', '支付宝', '高德', '美团', 'B站', '京东', '拼多多', '小红书', 'QQ', '设置']
  const colors = ['#07c160', '#000', '#ff5000', '#1677ff', '#00a0e9', '#ffc300', '#fb7299', '#e1251b', '#e02e24', '#ff2442', '#12b7f5', '#8a8a8a']

  // 真实设备大屏：ws-scrcpy iframe（MSE 视频流）
  if (isRedroid && !isError && !isStopped && large) {
    const scrcpyUrl = buildScrcpyUrl()
    return (
      <div className={`phone-screen real-screen ${streamStatus === 'error' ? 'screen-error-state' : ''}`} style={{ position: 'relative', background: '#000' }}>
        {scrcpyUrl ? (
          <iframe
            src={scrcpyUrl}
            style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
            onLoad={() => setStreamStatus('live')}
            allow="fullscreen"
          />
        ) : null}
        {streamStatus !== 'live' && (
          <div className="screen-loading" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
            <div className="loading-spinner" />
            <span>正在连接视频流...</span>
            <span style={{ fontSize: 10, opacity: 0.6 }}>{device.serial}</span>
          </div>
        )}
      </div>
    )
  }

  // 真实设备小卡片：截图
  if (isRedroid && !isError && !isStopped && !large) {
    return (
      <div className={`phone-screen real-screen ${ssError ? 'screen-error-state' : ''}`}>
        {screenshot && !ssError ? (
          <img src={screenshot} alt="device screen" className="screen-img" onError={() => setSsError(true)} />
        ) : (
          <div className="screen-loading">
            {ssError ? (
              <>
                <div className="err-icon" style={{ fontSize: 28 }}>⚠</div>
                <span>截图加载失败</span>
                <span style={{ fontSize: 10, opacity: 0.6 }}>{device.serial}</span>
              </>
            ) : (
              <>
                <div className="loading-spinner" />
                <span>加载中...</span>
              </>
            )}
          </div>
        )}
      </div>
    )
  }

  // 模拟器界面
  return (
    <div className={`phone-screen ${isError ? 'screen-error' : ''} ${isStopped ? 'screen-off' : ''}`}>
      <div className="status-bar">
        <span className="sb-time">{hh}:{mm}</span>
        <span className="sb-right">
          <span className="sb-signal">●●●●</span>
          <span className="sb-wifi">⌄⌄⌄</span>
          <span className="sb-battery">▮▮▮</span>
        </span>
      </div>
      {isError ? (
        <div className="screen-msg">
          <div className="err-icon">⚠</div>
          <div>设备离线</div>
          <div className="screen-sub">{device.serial}</div>
        </div>
      ) : isStopped ? (
        <div className="screen-msg">
          <div className="off-icon">⏻</div>
          <div>已关机</div>
        </div>
      ) : (
        <>
          <div className="phone-wallpaper">
            <div className="wp-clock">{hh}:{mm}</div>
            <div className="wp-date">{now.getMonth() + 1}月{now.getDate()}日 周{'日一二三四五六'[now.getDay()]}</div>
          </div>
          <div className="app-grid">
            {apps.map((name, i) => (
              <div key={i} className="app-icon">
                <div className="app-img" style={{ background: colors[i % colors.length] }}>{name.charAt(0)}</div>
                <span>{name}</span>
              </div>
            ))}
          </div>
          <div className="phone-dock">
            <div className="app-icon"><div className="app-img" style={{ background: '#07c160' }}>电</div><span>电话</span></div>
            <div className="app-icon"><div className="app-img" style={{ background: '#1677ff' }}>信</div><span>短信</span></div>
            <div className="app-icon"><div className="app-img" style={{ background: '#5856d6' }}>浏</div><span>浏览器</span></div>
            <div className="app-icon"><div className="app-img" style={{ background: '#8a8a8a' }}>相</div><span>相机</span></div>
          </div>
          <div className="home-indicator" />
        </>
      )}
    </div>
  )
}

/* ---------- 单台设备卡片 ---------- */
const STATUS_DOT = {
  running: { color: '#22c55e', label: '运行中' },
  creating: { color: '#3b82f6', label: '创建中' },
  stopped: { color: '#6b7280', label: '已停止' },
  error: { color: '#ef4444', label: '异常' },
}

function DeviceCard({ device, onControl, onDelete, onPreview, onPower, selectMode, selected, onToggleSelect }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)
  const isSelected = selectMode && selected?.has(device.id)

  // 点击外部关闭菜单
  useEffect(() => {
    function onClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const menuItems = [
    { label: '开机', icon: '⏻', action: () => onPower(device.id, 'start'), hide: device.status === 'running' },
    { label: '关机', icon: '⏼', action: () => onPower(device.id, 'stop'), hide: device.status === 'stopped' || device.status === 'error' },
    { label: '重启', icon: '↻', action: () => onPower(device.id, 'restart'), hide: device.status === 'stopped' || device.status === 'error' },
    { label: '删除', icon: '🗑', action: () => onDelete(device.id), danger: true },
  ].filter((m) => !m.hide)

  return (
    <div className={`device-card ${selectMode ? 'select-mode' : ''} ${isSelected ? 'selected' : ''}`}>
      <div className="phone-frame" onClick={() => (selectMode ? onToggleSelect(device.id) : onPreview(device))}>
        <PhoneScreen device={device} />
        <div className="card-name">
          <span className="card-name-text">{device.name}</span>
        </div>
        {selectMode && (
          <div className="select-check">
            <span className={`check-box ${isSelected ? 'checked' : ''}`}>{isSelected ? '✓' : ''}</span>
          </div>
        )}
      </div>
      <div className="card-menu" ref={menuRef}>
        <button
          className="menu-trigger"
          onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v) }}
          title="设备操作"
        >⋮</button>
        {menuOpen && (
          <div className="dropdown-menu" onClick={(e) => e.stopPropagation()}>
            {menuItems.map((m) => (
              <button
                key={m.label}
                className={`dropdown-item ${m.danger ? 'danger' : ''}`}
                onClick={() => { setMenuOpen(false); m.action() }}
              >
                <span className="dropdown-icon">{m.icon}</span>
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------- 导入真实设备弹窗 ---------- */
function ImportModal({ onClose, onImported }) {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    async function scan() {
      try {
        setLoading(true)
        const r = await api.discoverDevices()
        setDevices(r.data)
      } catch (e) {
        setErr(e.response?.data?.error || '扫描失败，请确认 ADB 已连接设备')
      } finally {
        setLoading(false)
      }
    }
    scan()
  }, [])

  async function handleImport(serial) {
    try {
      await api.importDevice({ serial })
      onImported()
      setDevices((prev) => prev.map((d) => d.serial === serial ? { ...d, already_imported: true } : d))
    } catch (e) {
      alert(e.response?.data?.error || '导入失败')
    }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal-body" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">
          <span>导入真实云手机</span>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        {loading && <div className="loading">正在扫描 ADB 设备...</div>}
        {err && <div className="err">{err}</div>}
        {!loading && !err && (
          <>
            <div className="muted" style={{ marginBottom: 12 }}>
              发现 {devices.length} 台在线设备，点击「导入」添加到看板
            </div>
            {devices.length === 0 && <div className="empty-hint">未发现已连接的 ADB 设备</div>}
            <div className="import-list">
              {devices.map((d) => (
                <div key={d.serial} className="import-item">
                  <div>
                    <div className="import-serial">{d.serial}</div>
                    <div className="import-meta">{d.model} · Android {d.android_version}</div>
                  </div>
                  {d.already_imported ? (
                    <span className="badge st-ok">已导入</span>
                  ) : (
                    <button onClick={() => handleImport(d.serial)}>导入</button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ---------- 大屏预览弹窗：方案3 · MST (WS scrcpy) 视频投屏 ---------- */
const MST_HOST = '192.168.9.131'
const MST_PORT = 8100

/* 线性图标（Feather 风格，stroke 随文字颜色） */
const Ic = ({ children }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
)

function PreviewModal({ device, onClose, onDelete }) {
  if (!device) return null

  // iframe 嵌入 MST 的 stream 页面（player=mse），触控由 MST 原生处理
  const port = (device.serial || '').split(':').pop() || '15555'
  const udid = `127.0.0.1:${port}`
  const ws = `ws://${MST_HOST}:${MST_PORT}/?action=proxy-adb&remote=tcp:8886&udid=${encodeURIComponent(udid)}`
  const streamUrl = `http://${MST_HOST}:${MST_PORT}/#!action=stream&udid=${encodeURIComponent(udid)}&player=mse&ws=${encodeURIComponent(ws)}`

  const sendKey = (keycode) => api.controlDevice(device.id, 'key', { keycode }).catch(() => {})
  const handleScreenshot = async () => {
    try {
      const r = await api.deviceScreenshot(device.id)
      const url = window.URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${device.name}_${Date.now()}.png`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (e) { console.error('截图失败', e) }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal-body modal-control" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">
          <span>{device.name} · 实时视频投屏</span>
        </div>
        <div className="modal-preview">
          <div className="mst-frame">
            <iframe
              src={streamUrl}
              title="云手机视频投屏"
              allow="autoplay; clipboard-read; clipboard-write; fullscreen"
            />
          </div>
          {/* 屏幕右侧竖向工具栏（放在云手机容器外侧，不遮挡画面） */}
          <div className="screen-toolbar" onClick={(e) => e.stopPropagation()}>
            <button className="st-btn" onClick={() => sendKey(4)} title="返回">
              <Ic><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></Ic>
            </button>
            <button className="st-btn" onClick={() => sendKey(3)} title="主页">
              <Ic><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></Ic>
            </button>
            <button className="st-btn" onClick={() => sendKey(187)} title="后台">
              <Ic><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></Ic>
            </button>
            <button className="st-btn" onClick={() => sendKey(24)} title="音量+">
              <Ic><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="15" y1="9" x2="15" y2="15"/><line x1="12" y1="12" x2="18" y2="12"/></Ic>
            </button>
            <button className="st-btn" onClick={() => sendKey(25)} title="音量-">
              <Ic><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="12" y1="12" x2="18" y2="12"/></Ic>
            </button>
            <button className="st-btn" onClick={() => sendKey(26)} title="电源">
              <Ic><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></Ic>
            </button>
            <button className="st-btn" onClick={handleScreenshot} title="截图">
              <Ic><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></Ic>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ---------- 主页面 ---------- */
export default function Devices() {
  const [list, setList] = useState([])
  const [name, setName] = useState('')
  const [count, setCount] = useState(5)
  const [backend, setBackend] = useState('redroid')
  const [err, setErr] = useState('')
  const [view, setView] = useState('grid')
  const [cardSize, setCardSize] = useState('compact')
  const [preview, setPreview] = useState(null)
  const [showImport, setShowImport] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const timerRef = useRef(null)
  // —— 批量选择模式 ——
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [scriptModal, setScriptModal] = useState(false)
  const [scripts, setScripts] = useState([])
  const [groupModal, setGroupModal] = useState(false)
  const [groups, setGroups] = useState([])
  const [groupTarget, setGroupTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const apkInputRef = useRef(null)
  // —— 轮次运行模式 ——
  const [rotation, setRotation] = useState({ enabled: false, rounds: 4, devices_per_round: 2, round_index: 1, per_round_hours: 6, next_round_at: null })
  const [rotBusy, setRotBusy] = useState(false)

  async function loadRotation() {
    try {
      const r = await api.getRotation()
      setRotation(r.data)
    } catch (e) {
      console.warn('获取轮次配置失败', e.response?.data?.error || e.message)
    }
  }

  async function handleRotationToggle(e) {
    const enabled = e.target.checked
    const n = Math.max(1, Math.min(200, Number(count) || 2))
    if (enabled) {
      const ok = window.confirm(
        `开启轮次运行后，将立即销毁现有云手机，并按「每轮 ${n} 台」重建；之后每轮结束自动销毁并重建 ${n} 台。确定开启？`
      )
      if (!ok) { e.target.checked = false; return }
    }
    setRotBusy(true)
    try {
      const r = await api.updateRotation({ enabled, devices_per_round: n })
      setRotation(r.data)
      if (enabled) alert('轮次运行已开启，正在按配置重置云手机，请稍候刷新设备列表…')
    } catch (err) {
      alert('设置失败：' + (err.response?.data?.error || err.message))
      loadRotation()
    } finally {
      setRotBusy(false)
    }
  }

  async function handleRotationRounds(e) {
    const rounds = Number(e.target.value)
    setRotBusy(true)
    try {
      const r = await api.updateRotation({ rounds })
      setRotation(r.data)
    } catch (err) {
      alert('设置轮数失败：' + (err.response?.data?.error || err.message))
      loadRotation()
    } finally {
      setRotBusy(false)
    }
  }

  async function load() {
    const r = await api.listDevices()
    setList(r.data)
  }
  async function loadGroups() {
    try {
      const r = await api.listGroups()
      setGroups(r.data || [])
    } catch (e) { /* 忽略 */ }
  }

  async function handleSync() {
    setSyncing(true)
    try {
      const r = await api.syncDevices()
      await load()
    } catch (e) {
      // 静默同步：失败不打扰用户
      console.warn('同步失败', e.response?.data?.error || e.message)
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    load()
    loadGroups()
    loadRotation()
    // 页面加载时自动同步一次
    handleSync()
    timerRef.current = setInterval(load, 5000)
    return () => clearInterval(timerRef.current)
  }, [])

  async function handleCreate(e) {
    e.preventDefault()
    setErr('')
    if (!name.trim()) { setErr('请输入设备名'); return }
    try {
      setErr(backend === 'redroid' ? '正在服务器上创建云手机容器，请稍候...' : '')
      await api.createDevice({ name: name.trim(), backend })
      setName('')
      setErr('')
      load()
    } catch (e) {
      setErr(e.response?.data?.error || '创建失败')
    }
  }

  async function handleBatch(e) {
    e.preventDefault()
    const n = Math.max(1, Math.min(200, Number(count) || 1))
    // 轮次运行已开启：按 count 台启动/重置本轮（销毁重建 + 重新计时）
    if (rotation.enabled) {
      if (!window.confirm(`轮次运行已开启，将按每轮 ${n} 台销毁并重建云手机，确定启动本轮？`)) return
      setRotBusy(true)
      try {
        const r = await api.updateRotation({ enabled: true, devices_per_round: n })
        setRotation(r.data)
        alert(`已按 ${n} 台启动本轮，正在重置，请稍候刷新设备列表…`)
      } catch (e2) {
        alert('启动本轮失败：' + (e2.response?.data?.error || e2.message))
        loadRotation()
      } finally {
        setRotBusy(false)
      }
      return
    }
    // 未开启：正常批量创建
    setErr('')
    try {
      setErr(backend === 'redroid' ? `正在批量创建 ${n} 台云手机容器，请稍候...` : '')
      await api.batchCreate({ count: n, prefix: 'redroid', backend })
      setErr('')
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
    alert(`${action} 指令已下发`)
    load()
  }

  async function handlePower(id, action) {
    const names = { start: '开机', stop: '关机', restart: '重启' }
    if (!confirm(`确认对该设备执行「${names[action]}」操作？`)) return
    try {
      await api.powerDevice(id, action)
      alert(`${names[action]}指令已下发`)
      load()
    } catch (e) {
      alert(`${names[action]}失败：${e.response?.data?.error || e.message}`)
    }
  }

  // —— 批量选择 / 操作 ——
  const selectedIds = [...selected]

  function enterSelectMode() {
    setSelectMode(true)
    setSelected(new Set())
  }
  function exitSelectMode() {
    setSelectMode(false)
    setSelected(new Set())
  }
  function toggleSelect(id) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  function selectAll() {
    if (selectedIds.length === list.length) setSelected(new Set())
    else setSelected(new Set(list.map((d) => d.id)))
  }

  async function handleBatchDelete() {
    if (!selectedIds.length) return
    if (!confirm(`确认删除选中的 ${selectedIds.length} 台云手机？`)) return
    setBusy(true)
    try {
      const r = await api.batchDelete(selectedIds)
      exitSelectMode()
      await load()
      alert(`删除完成：成功 ${r.data.ok} 台${r.data.failed ? `，失败 ${r.data.failed} 台` : ''}`)
    } catch (e) {
      setErr(e.response?.data?.error || '批量删除失败')
    } finally {
      setBusy(false)
    }
  }

  async function handleBatchRestart() {
    if (!selectedIds.length) return
    if (!confirm(`确认重启选中的 ${selectedIds.length} 台云手机？`)) return
    setBusy(true)
    try {
      const r = await api.batchPower(selectedIds, 'restart')
      await load()
      alert(`重启完成：成功 ${r.data.ok} 台${r.data.failed ? `，失败 ${r.data.failed} 台` : ''}`)
    } catch (e) {
      setErr(e.response?.data?.error || '批量重启失败')
    } finally {
      setBusy(false)
    }
  }

  async function openScriptModal() {
    try {
      const r = await api.listScripts()
      setScripts(Array.isArray(r.data) ? r.data : r.data.items || [])
      setScriptModal(true)
    } catch (e) {
      setErr(e.response?.data?.error || '加载脚本列表失败')
    }
  }
  async function runScript(sid) {
    setBusy(true)
    try {
      const r = await api.executeScript(sid, selectedIds)
      setScriptModal(false)
      await load()
      alert(`脚本执行完成：成功 ${r.data.ok} 台${r.data.failed ? `，失败 ${r.data.failed} 台` : ''}`)
    } catch (e) {
      setErr(e.response?.data?.error || '脚本执行失败')
    } finally {
      setBusy(false)
    }
  }

  async function handleApkFile(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.apk')) {
      setErr('仅支持 .apk 文件')
      return
    }
    if (!selectedIds.length) {
      setErr('请先选择设备')
      return
    }
    setBusy(true)
    try {
      const r = await api.installApk(selectedIds, file)
      alert(`APK 安装完成：成功 ${r.data.ok} 台${r.data.failed ? `，失败 ${r.data.failed} 台` : ''}`)
    } catch (e) {
      setErr(e.response?.data?.error || 'APK 安装失败')
    } finally {
      setBusy(false)
    }
  }

  async function handleSetGroup() {
    if (!selectedIds.length || groupTarget === undefined) return
    setBusy(true)
    try {
      const r = await api.batchSetGroup(selectedIds, groupTarget)
      setGroupModal(false)
      await load()
      alert(`已将 ${r.data.ok} 台设备${groupTarget == null ? '移出分组' : `加入分组「${groups.find((g) => g.id === groupTarget)?.name || ''}」`}`)
    } catch (e) {
      setErr(e.response?.data?.error || '设置分组失败')
    } finally {
      setBusy(false)
    }
  }

  // 状态统计
  const stats = [
    { key: 'running', label: '运行中', color: '#22c55e' },
    { key: 'stopped', label: '已停止', color: '#6b7280' },
    { key: 'creating', label: '创建中', color: '#3b82f6' },
    { key: 'error', label: '异常', color: '#ef4444' },
  ].map((s) => ({ ...s, count: list.filter((d) => d.status === s.key).length }))
  const totalCount = list.length

  return (
    <div>
      <div className="page-header">
        <div className="page-title">
          <h2>设备管理</h2>
          <span className="page-sub">{totalCount} 台云手机</span>
        </div>
        <div className="page-actions">
          <button className="ghost" onClick={() => api.downloadCsv("devices")}>导出 CSV</button>
          <button onClick={handleSync} disabled={syncing} className={`sync-btn ${syncing ? 'loading' : ''}`}>
            <span className="sync-icon">{syncing ? '⋯' : '↻'}</span>
            {syncing ? '同步中' : '同步'}
          </button>
          <button
            className={`select-btn ${selectMode ? 'active' : ''}`}
            onClick={() => (selectMode ? exitSelectMode() : enterSelectMode())}
          >
            {selectMode ? '退出选择' : '选择'}
          </button>
          <div className="view-toggle">
            <button className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')}>卡片</button>
            <button className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}>列表</button>
          </div>
        </div>
      </div>

      {selectMode && (
        <div className="batch-bar">
          <span className="batch-count">已选 <b>{selectedIds.length}</b> 台</span>
          <button className="batch-item ghost" onClick={selectAll}>
            {selectedIds.length === list.length ? '取消全选' : '全选'}
          </button>
          <div className="batch-spacer" />
          <button className="batch-item" onClick={handleBatchRestart} disabled={busy || !selectedIds.length}>重启</button>
          <button className="batch-item" onClick={openScriptModal} disabled={busy || !selectedIds.length}>执行脚本</button>
          <button className="batch-item" onClick={() => apkInputRef.current?.click()} disabled={busy || !selectedIds.length}>安装 APK</button>
          <button className="batch-item" onClick={() => { setGroupTarget(null); setGroupModal(true) }} disabled={busy || !selectedIds.length}>加入分组</button>
          <button className="batch-item danger" onClick={handleBatchDelete} disabled={busy || !selectedIds.length}>删除</button>
          <button className="batch-item ghost" onClick={exitSelectMode}>取消</button>
          <input ref={apkInputRef} type="file" accept=".apk,application/vnd.android.package-archive"
            style={{ display: 'none' }} onChange={handleApkFile} />
        </div>
      )}

      <div className="status-summary">
        {stats.map((s) => (
          <div className="status-chip" key={s.key}>
            <span className="status-dot" style={{ background: s.color }} />
            {s.label} <b>{s.count}</b>
          </div>
        ))}
      </div>

      {err && <div className="err">{err}</div>}

      <div className="toolbar">
        <div className="toolbar-group">
          <form onSubmit={handleCreate} className="inline">
            <input placeholder="设备名" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={backend} onChange={(e) => setBackend(e.target.value)} style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}>
              <option value="redroid">真实云手机</option>
              <option value="simulator">模拟设备</option>
            </select>
            <button type="submit">创建 1 台</button>
          </form>
        </div>
        <div className="layout-switch" title="卡片布局">
          <button className={cardSize === 'compact' ? 'active' : ''} onClick={() => setCardSize('compact')}>紧凑</button>
          <button className={cardSize === 'normal' ? 'active' : ''} onClick={() => setCardSize('normal')}>标准</button>
          <button className={cardSize === 'large' ? 'active' : ''} onClick={() => setCardSize('large')}>大图</button>
        </div>
        <div className="rotation-row">
          <form onSubmit={handleBatch} className="rotation-control"
            title={rotation.enabled ? '轮次运行已开启：按数量销毁并重建，启动本轮' : '批量创建'}>
            <input type="number" min="1" max="200" value={count}
              className="rotation-count"
              onChange={(e) => setCount(e.target.value)} disabled={rotBusy} />
            <button type="submit" className="rotation-submit" disabled={rotBusy}>
              {rotation.enabled ? '启动本轮' : '批量创建'}
            </button>
          </form>
          <div className={`rotation-control ${rotation.enabled ? 'on' : ''}`} title="轮次运行：一天分 N 轮，每轮结束自动销毁并按数量重建云手机（每轮台数用左侧输入框设置）">
            <label className="rotation-switch">
              <input type="checkbox" checked={rotation.enabled} onChange={handleRotationToggle} disabled={rotBusy} />
              <span className="rotation-slider" />
            </label>
            <span className="rotation-label">轮次运行</span>
            <select
              className="rotation-rounds"
              value={rotation.rounds}
              onChange={handleRotationRounds}
              disabled={rotBusy}
            >
              {[2, 3, 4, 6, 8, 12, 24].map((n) => (
                <option key={n} value={n}>{n}轮</option>
              ))}
            </select>
            {rotation.enabled && (
              <span className="rotation-info">
                第{rotation.round_index}轮 · 每{rotation.per_round_hours}h轮转 · 每轮{rotation.devices_per_round}台
                {rotation.next_round_at ? ` · 下次 ${new Date(rotation.next_round_at).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` : ''}
              </span>
            )}
          </div>
        </div>
      </div>

      {view === 'grid' ? (
        <div className={`device-grid ${cardSize}`}>
          {list.length === 0 && <div className="empty-hint">暂无设备，点击上方按钮创建</div>}
          {list.map((d) => (
            <DeviceCard key={d.id} device={d}
              onControl={handleControl} onDelete={handleDelete}
              onPreview={setPreview} onPower={handlePower}
              selectMode={selectMode} selected={selected} onToggleSelect={toggleSelect} />
          ))}
        </div>
      ) : (
        <div className="device-table-wrap">
          <table className="device-table">
            <thead>
              <tr>
                <th className="col-id">ID</th>
                <th>设备</th>
                <th>状态</th>
                <th>机型</th>
                <th>出口 IP</th>
                <th>Serial</th>
                <th className="col-ops">操作</th>
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <tr><td colSpan={7} className="table-empty">暂无设备，点击上方按钮创建</td></tr>
              ) : (
                list.map((d) => {
                  const st = STATUS_DOT[d.status] || { color: '#6b7280', label: d.status }
                  return (
                    <tr key={d.id} className="device-row" onClick={() => setPreview(d)}>
                      <td className="col-id mono">{d.id}</td>
                      <td>
                        <div className="cell-name">
                          <span className="name-text">{d.name}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`status-dot status-dot-lg ${d.status}`} style={{ background: st.color }} title={st.label} />
                      </td>
                      <td>
                        <span className="model-cell">{d.model || '—'}</span>
                      </td>
                      <td className="mono">{d.ip || '—'}</td>
                      <td className="mono serial-cell" title={d.serial}>{d.serial || '—'}</td>
                      <td className="col-ops" onClick={(e) => e.stopPropagation()}>
                        <div className="row-ops">
                          <button className="op-btn" title="打开预览" onClick={() => setPreview(d)}>👁</button>
                          <button className="op-btn" title="重启" onClick={() => handlePower(d.id, 'restart')}>↻</button>
                          <button className="op-btn danger" title="删除" onClick={() => handleDelete(d.id)}>🗑</button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      <PreviewModal
        device={preview}
        onClose={() => setPreview(null)}
        onDelete={(id) => {
          setPreview(null)
          handleDelete(id)
        }}
      />
      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={load} />}

      {/* 批量执行脚本弹窗 */}
      {scriptModal && (
        <div className="modal-mask" onClick={() => setScriptModal(false)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>执行脚本 · 已选 {selectedIds.length} 台</span>
              <button className="modal-close" onClick={() => setScriptModal(false)}>✕</button>
            </div>
            {scripts.length === 0 ? (
              <div className="empty-hint" style={{ padding: 30 }}>
                暂无脚本，请先在「脚本管理」创建脚本
              </div>
            ) : (
              <div className="script-pick-list">
                {scripts.map((s) => (
                  <div className="script-pick-item" key={s.id}>
                    <div className="script-pick-info">
                      <div className="script-pick-name">{s.name}</div>
                      <div className="script-pick-meta">{(s.steps?.length || 0)} 步</div>
                    </div>
                    <button onClick={() => runScript(s.id)} disabled={busy}>执行</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 批量加入分组弹窗 */}
      {groupModal && (
        <div className="modal-mask" onClick={() => setGroupModal(false)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span>加入分组 · 已选 {selectedIds.length} 台</span>
              <button className="modal-close" onClick={() => setGroupModal(false)}>✕</button>
            </div>
            <div className="push-sec-title">选择目标分组</div>
            <div className="dev-pick push-group-pick">
              <label className="chip">
                <input
                  type="radio"
                  name="groupTarget"
                  checked={groupTarget === null}
                  onChange={() => setGroupTarget(null)}
                />
                <b>移出分组（未分组）</b>
              </label>
              {groups.map((g) => (
                <label key={g.id} className="chip">
                  <input
                    type="radio"
                    name="groupTarget"
                    checked={groupTarget === g.id}
                    onChange={() => setGroupTarget(g.id)}
                  />
                  <b>{g.name}</b>
                  <span className="chip-sub">{g.device_count} 台</span>
                </label>
              ))}
              {groups.length === 0 && <p className="hint">暂无分组，可先到「分组管理」创建</p>}
            </div>
            <div className="modal-actions">
              <button className="ghost" onClick={() => setGroupModal(false)} disabled={busy}>取消</button>
              <button onClick={handleSetGroup} disabled={busy || groupTarget === undefined}>确定</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
