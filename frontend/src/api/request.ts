import axios from 'axios'
import { useMessage } from 'naive-ui'
import router from '@/router'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: automatically attach Token
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// Response interceptor: unified error handling
request.interceptors.response.use(
  (response) => {
    const data = response.data
    // Business layer errors
    if (data && data.code !== undefined && data.code !== 0) {
      return Promise.reject(new Error(data.msg || 'Request failed'))
    }
    return data
  },
  (error) => {
    const status = error.response?.status
    const msg = error.response?.data?.detail || error.message || 'Network error'

    if (status === 401) {
      // The login endpoint itself returns 401 for wrong credentials — don't
      // treat that as a session expiry. For all other endpoints a 401 means
      // the JWT has expired or been invalidated.
      const url = error.config?.url ?? ''
      if (!url.includes('/auth/login')) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        router.push('/login')
        return Promise.reject(new Error('Session expired. Please log in again.'))
      }
      // Fall through so the actual backend message is returned below.
    }

    if (status === 403) {
      return Promise.reject(new Error('Access denied'))
    }

    if (status === 404) {
      return Promise.reject(new Error('Resource not found'))
    }

    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  },
)

export default request
