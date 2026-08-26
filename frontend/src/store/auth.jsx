import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('user') || 'null')
    } catch {
      return null
    }
  })
  const [token, setToken] = useState(() => localStorage.getItem('token') || '')
  const [ready, setReady] = useState(false)

  // 启动时若有 token，拉一次 /auth/me 校验并刷新 user
  useEffect(() => {
    if (token && !user) {
      api
        .me()
        .then((r) => setUser(r.data))
        .catch(() => logout())
        .finally(() => setReady(true))
    } else {
      setReady(true)
    }
  }, [])

  // 监听后端 401 触发的登出事件
  useEffect(() => {
    const onLogout = () => logout()
    window.addEventListener('auth:logout', onLogout)
    return () => window.removeEventListener('auth:logout', onLogout)
  }, [])

  async function login(username, password) {
    const { data } = await api.login(username, password)
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }

  function logout() {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken('')
    setUser(null)
  }

  const isAuthed = !!token && !!user

  return (
    <AuthContext.Provider value={{ user, token, isAuthed, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
