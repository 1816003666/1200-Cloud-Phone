import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth.jsx'

const ROLE_RANK = { viewer: 1, operator: 2, admin: 3, superadmin: 4 }

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isAdmin = ROLE_RANK[user?.role] >= ROLE_RANK.admin

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">云手机看板</div>
        <nav>
          <NavLink to="/dashboard" className={({ isActive }) => (isActive ? 'active' : '')}>
            数据看板
          </NavLink>
          <NavLink to="/devices" className={({ isActive }) => (isActive ? 'active' : '')}>
            设备管理
          </NavLink>
          <NavLink to="/tasks" className={({ isActive }) => (isActive ? 'active' : '')}>
            任务调度
          </NavLink>
          <NavLink to="/files" className={({ isActive }) => (isActive ? 'active' : '')}>
            文件管理
          </NavLink>
          <NavLink to="/scripts" className={({ isActive }) => (isActive ? 'active' : '')}>
            脚本管理
          </NavLink>
          <NavLink to="/groups" className={({ isActive }) => (isActive ? 'active' : '')}>
            分组管理
          </NavLink>
          {/* 用户管理 / 审计日志 仅 admin 及以上可见 */}
          {isAdmin && (
            <NavLink to="/users" className={({ isActive }) => (isActive ? 'active' : '')}>
              用户管理
            </NavLink>
          )}
          {isAdmin && (
            <NavLink to="/audit" className={({ isActive }) => (isActive ? 'active' : '')}>
              审计日志
            </NavLink>
          )}
          {isAdmin && (
            <NavLink to="/alerts" className={({ isActive }) => (isActive ? 'active' : '')}>
              告警中心
            </NavLink>
          )}
        </nav>
        <div className="user-box">
          <div>{user?.username}（{user?.role}）</div>
          <button onClick={handleLogout}>退出</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
