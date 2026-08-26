import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useAuth } from '../store/auth.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    try {
      await login(username, password)
      const redirect = params.get('redirect') || '/dashboard'
      navigate(redirect)
    } catch (e) {
      setErr(e.response?.data?.error || '登录失败')
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={handleSubmit}>
        <h2>云手机平台 · 登录</h2>
        {err && <div className="err">{err}</div>}
        <input
          placeholder="用户名"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          placeholder="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit">登录</button>
        <p className="hint">默认账号：admin / Admin@123456</p>
        <p className="hint">
          还没有账号？<Link to="/register">去注册</Link>
        </p>
      </form>
    </div>
  )
}
