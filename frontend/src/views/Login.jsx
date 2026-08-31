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
  const [captcha, setCaptcha] = useState(null)   // {captcha_id, question}
  const [captchaAns, setCaptchaAns] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    try {
      await login(username, password, captcha ? { captcha_id: captcha.captcha_id, captcha: captchaAns } : {})
      const redirect = params.get('redirect') || '/dashboard'
      navigate(redirect)
    } catch (e) {
      const data = e.response?.data
      setErr(data?.error || '登录失败')
      if (data?.need_captcha && data?.captcha) {
        setCaptcha(data.captcha)
        setCaptchaAns('')
      }
      if (e.response?.status === 423) {
        setCaptcha(null)
        setCaptchaAns('')
      }
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <span className="logo-mark" />
          <div>
            <h2>云手机平台</h2>
            <div className="login-subtitle">批量设备管理 · 实时操控 · 任务调度</div>
          </div>
        </div>
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
        {captcha && (
          <div className="login-captcha">
            <span className="captcha-q">{captcha.question}</span>
            <input
              placeholder="验证码答案"
              value={captchaAns}
              onChange={(e) => setCaptchaAns(e.target.value)}
            />
          </div>
        )}
        <button type="submit">登录</button>
        <p className="hint">默认账号：admin / Admin@123456</p>
        <p className="hint">
          还没有账号？<Link to="/register">去注册</Link>
        </p>
      </form>
    </div>
  )
}
