/**
 * Axios API client - all backend API calls go through here.
 */
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('et_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Normalize error responses
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const login = (username, password) =>
  api.post('/auth/login', { username, password }, { auth: { username, password } })

export const register = (username, email, password) =>
  api.post('/auth/register', { username, email, password })

export const getMe = () => api.get('/auth/me')

// ── Predictions ────────────────────────────────────────────────────────────────

export const predictSession = (payload) =>
  api.post('/predict-session', payload)

// ── Pipeline ─────────────────────────────────────────────────────────────────

export const rebuildPipeline = (payload) =>
  api.post('/pipeline/rebuild', payload)

// ── Tasks ─────────────────────────────────────────────────────────────────────

export const getTaskRecords = (params) =>
  api.get('/tasks', { params })

// ── Realtime ─────────────────────────────────────────────────────────────────

export const getMonitorStatus = () => api.get('/realtime/monitor/status')

export const startMonitor = (payload) => api.post('/realtime/monitor/start', payload)

export const stopMonitor = () => api.post('/realtime/monitor/stop')

export const getRealtimePredictions = (limit = 50) =>
  api.get('/realtime/predictions', { params: { limit } })

// ── System ───────────────────────────────────────────────────────────────────

export const getSystemInfo = () => api.get('/system/info')

export const getLogs = (limit = 50) => api.get('/system/logs', { params: { limit } })

// ── AI Advice (streaming) ─────────────────────────────────────────────────────

export const getAIAdviceStream = (sessionFilter = '') => {
  const token = localStorage.getItem('et_token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return fetch(`${BASE_URL}/ai/advice`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ session_filter: sessionFilter }),
  })
}

export default api
