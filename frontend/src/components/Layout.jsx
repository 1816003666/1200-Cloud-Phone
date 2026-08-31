import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth.jsx'

const ROLE_RANK = { viewer: 1, operator: 2, admin: 3, superadmin: 4 }

// 极简线性图标（16x16，stroke）
const Icon = ({ d }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d={d} />
  </svg>
)

const NAV_ICONS = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  devices: 'M5 2h14a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm7 18h.01',
  tasks: 'M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',
  files: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8',
  scripts: 'M16 18l6-6-6-6 M8 6l-6 6 6 6',
  groups: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
  users: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  audit: 'M12 8v4l3 3 M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z',
  alerts: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01',
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isAdmin = ROLE_RANK[user?.role] >= ROLE_RANK.admin

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const navGroups = [
    {
      title: '设备运营',
      items: [
        { to: '/dashboard', label: '数据看板', icon: NAV_ICONS.dashboard },
        { to: '/devices', label: '设备管理', icon: NAV_ICONS.devices },
        { to: '/tasks', label: '任务调度', icon: NAV_ICONS.tasks },
      ],
    },
    {
      title: '资源管理',
      items: [
        { to: '/files', label: '文件管理', icon: NAV_ICONS.files },
        { to: '/scripts', label: '脚本管理', icon: NAV_ICONS.scripts },
        { to: '/groups', label: '分组管理', icon: NAV_ICONS.groups },
      ],
    },
    {
      title: '系统管理',
      admin: true,
      items: [
        { to: '/users', label: '用户管理', icon: NAV_ICONS.users },
        { to: '/audit', label: '审计日志', icon: NAV_ICONS.audit },
        { to: '/alerts', label: '告警中心', icon: NAV_ICONS.alerts },
        { to: '/settings', label: '系统设置', icon: NAV_ICONS.audit },
      ],
    },
  ]

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-mark" />
          <span>云手机看板</span>
        </div>
        <nav>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              {group.admin && !isAdmin ? null : (
                <>
                  <div className="nav-group-title">{group.title}</div>
                  {group.items.map((item) => (
                    <NavLink key={item.to} to={item.to}
                      className={({ isActive }) => (isActive ? 'active' : '')}>
                      <Icon d={item.icon} />
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </>
              )}
            </div>
          ))}
        </nav>
        <div className="user-box">
          <div className="user-chip">
            <span className="user-avatar">{(user?.username || '?').slice(0, 1).toUpperCase()}</span>
            <span className="user-meta">
              <span className="user-name">{user?.username}</span>
              <span className="user-role">{user?.role}</span>
            </span>
          </div>
          <button className="logout-btn" onClick={handleLogout}>
            <Icon d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9" />
            <span className="btn-text">退出登录</span>
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
