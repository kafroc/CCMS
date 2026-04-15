import request from './request'
import axios from 'axios'

export interface TOE {
  id: string
  name: string
  access_level?: string
  toe_type: string
  version: string | null
  brief_intro: string | null
  // Active fields
  toe_type_desc: string | null
  toe_usage: string | null
  major_security_features: string | null
  required_non_toe_hw_sw_fw: string | null
  physical_scope: string | null
  logical_scope: string | null
  hw_interfaces: string | null
  sw_interfaces: string | null
  ai_generated_at: string | null
  created_at: string | null
  updated_at: string | null
  asset_count?: number
  file_count?: number
}

export interface TOEAsset {
  id: string
  toe_id: string
  name: string
  description: string | null
  asset_type: string
  importance: number
  importance_reason: string | null
  ai_generated: boolean
  weak_coverage_ignored: boolean
  created_at: string | null
}

export interface TOEFile {
  id: string
  toe_id: string
  original_filename: string
  file_type: string
  file_category: string   // manual | st_pp | other
  mime_type: string
  file_size: number
  process_status: string
  process_error: string | null
  created_at: string | null
}

export interface CascadeCounts {
  asset_count: number
  file_count: number
  threat_count: number
  assumption_count: number
  osp_count: number
  objective_count: number
  sfr_count: number
  test_count: number
  risk_count: number
}

export const toeApi = {
  // ── TOE CRUD ──
  list(params?: { search?: string; toe_type?: string }) {
    return request.get<any, { code: number; data: TOE[] }>('/toes', { params })
  },
  get(id: string) {
    return request.get<any, { code: number; data: TOE }>(`/toes/${id}`)
  },
  create(data: Record<string, any>) {
    return request.post<any, { code: number; data: TOE }>('/toes', data)
  },
  update(id: string, data: Record<string, any>) {
    return request.put<any, { code: number; data: TOE }>(`/toes/${id}`, data)
  },
  delete(id: string) {
    return request.delete<any, { code: number; data: CascadeCounts }>(`/toes/${id}`)
  },
  getCascadeCounts(id: string) {
    return request.get<any, { code: number; data: CascadeCounts }>(`/toes/${id}/cascade-counts`)
  },
  async exportPackage(id: string) {
    const token = localStorage.getItem('token')
    const response = await axios.get(`/api/toes/${id}/package/export`, {
      responseType: 'blob',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
    return response.data as Blob
  },
  importPackage(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post<any, { code: number; data: { id: string; name: string; summary: Record<string, number> } }>(
      '/toes/package/import',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      },
    )
  },

  // ── AI description generation ──
  aiGenerateDescription(id: string, language: 'zh' | 'en' = 'en') {
    return request.post<any, { code: number; data: Record<string, string> }>(
      `/toes/${id}/ai-generate-description`,
      { language },
      { timeout: 0 },
    )
  },

  // ── AI description generation (draft, no existing TOE required) ──
  aiGenerateDescriptionDraft(data: { name: string; toe_type: string; brief_intro: string; version?: string; language?: 'zh' | 'en' }) {
    return request.post<any, { code: number; data: Record<string, string> }>(
      `/toes/ai-generate-description-draft`,
      data,
      { timeout: 0 },
    )
  },

  // ── AI document analysis (single file, extract fields by type) ──
  aiAnalyzeDoc(toeId: string, fileId: string, focus: 'st_pp' | 'manual', language: string = 'en') {
    return request.post<any, { code: number; data: Record<string, string> }>(
      `/toes/${toeId}/ai-analyze-docs`,
      { file_id: fileId, focus, language },
      { timeout: 600000 }, // 10 minute timeout to accommodate PDF extraction + AI processing
    )
  },

  // ── AI document async analysis (returns task ID, frontend polls) ──
  aiAnalyzeDocAsync(toeId: string, fileId: string, focus: 'st_pp' | 'manual', language: string = 'en') {
    return request.post<any, { code: number; data: { task_id: string } }>(
      `/toes/${toeId}/ai-analyze-docs-async`,
      { file_id: fileId, focus, language },
      { timeout: 30000 }, // Only wait for task ID return, no need to wait for completion
    )
  },

  // ── AI consolidation (merge and deduplicate all fields) ──
  aiConsolidate(toeId: string, language: 'zh' | 'en' = 'en') {
    return request.post<any, { code: number; data: Record<string, string> }>(
      `/toes/${toeId}/ai-consolidate`,
      { language },
      { timeout: 0 },
    )
  },

  // ── AI consolidate specified fields ──
  aiConsolidateFields(toeId: string, fields: string[], language: 'zh' | 'en' = 'en') {
    return request.post<any, { code: number; data: Record<string, string> }>(
      `/toes/${toeId}/ai-consolidate-fields`,
      { fields, language },
      { timeout: 0 },
    )
  },

  // ── Asset CRUD ──
  listAssets(toeId: string) {
    return request.get<any, { code: number; data: TOEAsset[] }>(`/toes/${toeId}/assets`)
  },
  createAsset(toeId: string, data: Record<string, any>) {
    return request.post<any, { code: number; data: TOEAsset }>(`/toes/${toeId}/assets`, data)
  },
  updateAsset(toeId: string, assetId: string, data: Record<string, any>) {
    return request.put<any, { code: number; data: TOEAsset }>(
      `/toes/${toeId}/assets/${assetId}`, data
    )
  },
  deleteAsset(toeId: string, assetId: string) {
    return request.delete(`/toes/${toeId}/assets/${assetId}`)
  },
  aiSuggestAssets(toeId: string, language: string = 'en') {
    return request.post<any, { code: number; data: any[] }>(`/toes/${toeId}/assets/ai-suggest?language=${language}`)
  },
  translateToEnglish(content: Record<string, string>) {
    return request.post<any, { code: number; data: Record<string, string> }>('/toes/ai/translate-to-english', content)
  },

  // ── File CRUD ──
  listFiles(toeId: string, fileCategory?: string) {
    const params: any = {}
    if (fileCategory) params.file_category = fileCategory
    return request.get<any, { code: number; data: TOEFile[] }>(`/toes/${toeId}/files`, { params })
  },
  uploadFile(toeId: string, file: File, fileCategory: string = 'manual') {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('file_category', fileCategory)
    return request.post<any, { code: number; data: any }>(`/toes/${toeId}/files`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  deleteFile(toeId: string, fileId: string) {
    return request.delete(`/toes/${toeId}/files/${fileId}`)
  },
  getFileStatus(toeId: string, fileId: string) {
    return request.get<any, { code: number; data: { id: string; process_status: string; process_error: string | null } }>(
      `/toes/${toeId}/files/${fileId}/status`
    )
  },
}
