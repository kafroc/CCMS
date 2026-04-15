import request from './request'

export interface SystemSettingItem {
  value: string
  label: string
  type: 'int' | 'string'
  min?: number
  max?: number
}

export type SystemSettings = Record<string, SystemSettingItem>

export interface AuditLogItem {
  id: string
  created_at: string | null
  username: string | null
  user_id: string | null
  method: string
  path: string
  status_code: number
  resource: string | null
  resource_id: string | null
  ip: string | null
  duration_ms: number | null
}

export interface ErrorLogItem {
  id: string
  created_at: string | null
  level: string
  error_type: string
  message: string
  stack_trace: string | null
  username: string | null
  user_id: string | null
  method: string | null
  path: string | null
  ip: string | null
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AuditLogQuery {
  page?: number
  page_size?: number
  username?: string
  method?: string
  resource?: string
  status_min?: number
  status_max?: number
}

export interface ErrorLogQuery {
  page?: number
  page_size?: number
  level?: string
  error_type?: string
}

export const systemApi = {
  getSettings() {
    return request.get<any, { code: number; data: SystemSettings }>('/system/settings')
  },
  updateSettings(payload: Record<string, string | number>) {
    return request.patch<any, { code: number; data: SystemSettings }>('/system/settings', payload)
  },
  getAuditLogs(params: AuditLogQuery = {}) {
    return request.get<any, { code: number; data: Paginated<AuditLogItem> }>('/system/logs/audit', { params })
  },
  getErrorLogs(params: ErrorLogQuery = {}) {
    return request.get<any, { code: number; data: Paginated<ErrorLogItem> }>('/system/logs/errors', { params })
  },
  clearAuditLogs(before_days = 30) {
    return request.delete<any, { code: number; data: { deleted: number } }>('/system/logs/audit', { params: { before_days } })
  },
  clearErrorLogs(before_days = 30) {
    return request.delete<any, { code: number; data: { deleted: number } }>('/system/logs/errors', { params: { before_days } })
  },
}
