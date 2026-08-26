import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import Login from './views/Login.jsx'
import Register from './views/Register.jsx'
import Dashboard from './views/Dashboard.jsx'
import Devices from './views/Devices.jsx'
import Tasks from './views/Tasks.jsx'
import Users from './views/Users.jsx'
import Files from './views/Files.jsx'
import Scripts from './views/Scripts.jsx'
import Groups from './views/Groups.jsx'
import Audit from './views/Audit.jsx'
import Alerts from './views/Alerts.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/files" element={<Files />} />
        <Route path="/scripts" element={<Scripts />} />
        <Route path="/groups" element={<Groups />} />
        {/* 用户管理 / 审计日志 仅 admin 及以上可见（Layout 内也做了显隐） */}
        {<Route path="/users" element={<Users />} />}
        {<Route path="/audit" element={<Audit />} />}
        {<Route path="/alerts" element={<Alerts />} />}
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
