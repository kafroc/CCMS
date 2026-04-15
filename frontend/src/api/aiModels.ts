import request from './request'

export interface AIModel {
  id: string
  name: string
  api_base: string
  api_key_masked: string
  model_name: string
  is_verified: boolean
  verified_at: string | null
  timeout_seconds: number
  is_active: boolean
  created_at: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export const aiModelApi = {
  list() {
    return request.get<any, { code: number; data: AIModel[] }>('/ai-models')
  },

  create(data: { name: string; api_base: string; api_key: string; model_name: string; timeout_seconds?: number }) {
    return request.post<any, { code: number; data: AIModel }>('/ai-models', data)
  },

  update(id: string, data: { name?: string; api_base?: string; api_key?: string; model_name?: string; timeout_seconds?: number }) {
    return request.put<any, { code: number; data: AIModel }>(`/ai-models/${id}`, data)
  },

  delete(id: string) {
    return request.delete(`/ai-models/${id}`)
  },

  verify(id: string) {
    return request.post<any, { code: number; data: AIModel; msg: string }>(`/ai-models/${id}/verify`)
  },

  setActive(id: string) {
    return request.post<any, { code: number; data: AIModel; msg: string }>(`/ai-models/${id}/set-active`)
  },

  chat(id: string, messages: ChatMessage[]) {
    return request.post<any, { code: number; data: { content: string; role: string } }>(
      `/ai-models/${id}/chat`,
      { messages },
      { timeout: 120000 },
    )
  },
}
