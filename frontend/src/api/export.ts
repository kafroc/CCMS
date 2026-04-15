import request from './request'

const base = (toeId: string) => `/toes/${toeId}`

export const exportApi = {
  /** Get rendered ST preview (markdown) for a TOE */
  getSTPreview: (toeId: string) =>
    request.get<any, { code: number; data: { content: string } }>(`${base(toeId)}/st-preview`),

  /** Export ST document (returns file download) */
  exportST: (toeId: string, format: 'md' | 'docx', content?: string) =>
    request.post(`${base(toeId)}/export-st`, { format, content }, { responseType: 'blob' }),

  /** Get current ST template */
  getSTTemplate: () =>
    request.get<any, { code: number; data: { content: string } }>('/st-template'),

  /** Update ST template */
  updateSTTemplate: (content: string) =>
    request.put<any, { code: number }>('/st-template', { content }),

  /** Get default ST template */
  getDefaultSTTemplate: () =>
    request.get<any, { code: number; data: { content: string } }>('/st-template/default'),

  /** Legacy download URL */
  getDownloadUrl: (toeId: string, taskId: string) =>
    `/api/toes/${toeId}/export-st/download/${taskId}`,
}
