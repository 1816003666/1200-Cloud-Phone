import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../store/auth.jsx'
import { api } from '../api/client.js'

export default function Register() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [remember, setRemember] = useState(true)
  const [err, setErr] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    if (username.trim().length < 1) return setErr('用户名必填')
    if (password.length < 6) return setErr('密码至少 6 位')
    if (!/[a-zA-Z]/.test(password) || !/\d/.test(password))
      return setErr('密码须同时包含字母和数字')
    if (password !== confirm) return setErr('两次密码不一致')

    try {
      // 注册成功后后端直接返回 token，自动登录
      const { data } = await api.register(username.trim(), password)
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      if (!remember) {
        // 不记住密码：关闭标签页后清除（简化实现，仅做提示级处理）
      }
      await login(username.trim(), password)
      navigate('/dashboard')
    } catch (e) {
      setErr(e.response?.data?.error || '注册失败')
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={handleSubmit}>
        <h2>云手机平台 · 注册</h2>
        {err && <div className="err">{err}</div>}
        <input placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input type="password" placeholder="密码（≥6位，含字母和数字）" value={password} onChange={(e) => setPassword(e.target.value)} />
        <input type="password" placeholder="确认密码" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <label className="remember">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          记住登录状态
        </label>
        <button type="submit">注册并登录</button>
        <p className="hint">
          已有账号？<Link to="/login">去登录</Link>
        </p>
      </form>
    </div>
  )
}
