import axios from 'axios'

// 所有请求走 /api，本地由 vite 代理转发到后端 8000
const http = axios.create({ baseURL: '/api', timeout: 60000 })

// 注入 JWT
http.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// 401 自动登出 + 跳登录页
let handling401 = false
http.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err.response?.status
    const url = err.config?.url || ''
    if (status === 401 && !url.includes('/auth/login') && !handling401) {
      handling401 = true
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      // 同步清 store（若存在），避免路由守卫误判已登录
      window.dispatchEvent(new Event('auth:logout'))
      setTimeout(() => (handling401 = false), 1000)
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export const api = {
  login: (username, password) => http.post('/auth/login', { username, password }),
  me: () => http.get('/auth/me'),

  listDevices: (params) => http.get('/devices', { params }),
  createDevice: (body) => http.post('/devices', body),
  batchCreate: (body) => http.post('/devices/batch', body),
  deleteDevice: (id) => http.delete(`/devices/${id}`),
  controlDevice: (id, action, body) => http.post(`/devices/${id}/control/${action}`, body),

  listTasks: () => http.get('/tasks'),
  createTask: (body) => http.post('/tasks', body),
  runTask: (id) => http.post(`/tasks/${id}/run`),
  deleteTask: (id) => http.delete(`/tasks/${id}`),

  listUsers: () => http.get('/users'),
  createUser: (body) => http.post('/users', body),
  updateUser: (id, body) => http.patch(`/users/${id}`, body),
  deleteUser: (id) => http.delete(`/users/${id}`),

  // —— 注册（任务书 #13）——
  register: (username, password) => http.post('/auth/register', { username, password }),

  // —— 文件管理（任务书 #8）——
  uploadFile: (file, onProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/files/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    })
  },
  listFiles: (params) => http.get('/files', { params }),
  downloadFile: (id, filename) =>
    http.get(`/files/${id}/download`, { responseType: 'blob' }).then((r) => {
      const url = window.URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = filename || `file_${id}`
      a.click()
      window.URL.revokeObjectURL(url)
    }),
  deleteFile: (id) => http.delete(`/files/${id}`),
  pushFile: (id, deviceIds) => http.post(`/files/${id}/push`, { device_ids: deviceIds }),

  // —— 脚本管理（任务书 #9）——
  listScripts: () => http.get('/scripts'),
  scriptTemplates: () => http.get('/scripts/templates'),
  createScript: (body) => http.post('/scripts', body),
  updateScript: (id, body) => http.patch(`/scripts/${id}`, body),
  deleteScript: (id) => http.delete(`/scripts/${id}`),
  executeScript: (id, deviceIds) => http.post(`/scripts/${id}/execute`, { device_ids: deviceIds }),

  // —— 分组管理（任务书 #10）——
  listGroups: () => http.get('/groups'),
  createGroup: (body) => http.post('/groups', body),
  updateGroup: (id, body) => http.patch(`/groups/${id}`, body),
  deleteGroup: (id) => http.delete(`/groups/${id}`),
  groupBatchAction: (id, body) => http.post(`/groups/${id}/batch-action`, body),

  // —— 审计日志（任务书 #11）——
  listAudit: (params) => http.get('/audit', { params }),
  auditStats: () => http.get('/audit/stats'),

  // —— 告警系统（任务书 #12）——
  listAlerts: (params) => http.get('/alerts', { params }),
  alertSummary: () => http.get('/alerts/summary'),
  ackAlert: (id) => http.post(`/alerts/${id}/ack`),
  resolveAlert: (id) => http.post(`/alerts/${id}/resolve`),

  overview: () => http.get('/metrics/overview'),
}

export default http
