/**
 * Unit tests for the system API helpers (settings + logs).
 *
 * Axios is mocked via vi.mock so tests never hit the network.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the axios request module before importing systemApi.
vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import request from '@/api/request'
import { systemApi } from '@/api/system'

const mockGet = vi.mocked(request.get)
const mockPatch = vi.mocked(request.patch)
const mockDelete = vi.mocked(request.delete)

beforeEach(() => vi.clearAllMocks())

describe('systemApi.getSettings', () => {
  it('calls GET /system/settings', async () => {
    mockGet.mockResolvedValue({ code: 0, data: { pdf_parse_timeout_seconds: { value: '300', label: 'Timeout', type: 'int' } } })
    const res = await systemApi.getSettings()
    expect(mockGet).toHaveBeenCalledWith('/system/settings')
    expect(res.data.pdf_parse_timeout_seconds.value).toBe('300')
  })
})

describe('systemApi.updateSettings', () => {
  it('calls PATCH /system/settings with payload', async () => {
    mockPatch.mockResolvedValue({ code: 0, data: { pdf_parse_timeout_seconds: { value: '600', label: 'Timeout', type: 'int' } } })
    const res = await systemApi.updateSettings({ pdf_parse_timeout_seconds: 600 })
    expect(mockPatch).toHaveBeenCalledWith('/system/settings', { pdf_parse_timeout_seconds: 600 })
    expect(res.data.pdf_parse_timeout_seconds.value).toBe('600')
  })
})

describe('systemApi.getAuditLogs', () => {
  it('calls GET /system/logs/audit with no params by default', async () => {
    mockGet.mockResolvedValue({ code: 0, data: { items: [], total: 0, page: 1, page_size: 20 } })
    await systemApi.getAuditLogs()
    expect(mockGet).toHaveBeenCalledWith('/system/logs/audit', { params: {} })
  })

  it('forwards filter params', async () => {
    mockGet.mockResolvedValue({ code: 0, data: { items: [], total: 0, page: 1, page_size: 20 } })
    await systemApi.getAuditLogs({ method: 'POST', page: 2 })
    expect(mockGet).toHaveBeenCalledWith('/system/logs/audit', { params: { method: 'POST', page: 2 } })
  })
})

describe('systemApi.getErrorLogs', () => {
  it('calls GET /system/logs/errors', async () => {
    mockGet.mockResolvedValue({ code: 0, data: { items: [], total: 0, page: 1, page_size: 20 } })
    await systemApi.getErrorLogs({ level: 'ERROR' })
    expect(mockGet).toHaveBeenCalledWith('/system/logs/errors', { params: { level: 'ERROR' } })
  })
})

describe('systemApi.clearAuditLogs', () => {
  it('calls DELETE /system/logs/audit with before_days param', async () => {
    mockDelete.mockResolvedValue({ code: 0, data: { deleted: 5 } })
    const res = await systemApi.clearAuditLogs(30)
    expect(mockDelete).toHaveBeenCalledWith('/system/logs/audit', { params: { before_days: 30 } })
    expect(res.data.deleted).toBe(5)
  })
})
