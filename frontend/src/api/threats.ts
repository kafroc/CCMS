import request from './request'

export interface Threat {
  id: string; toe_id: string; code: string
  threat_agent: string | null; adverse_action: string | null; assets_affected: string | null
  asset_ids: string[]
  linked_assets: Array<{ id: string; name: string; asset_type: string; importance: number }>
  likelihood: string; impact: string; risk_level: string; risk_overridden: boolean
  review_status: string; ai_rationale: string | null; ai_source_ref: string | null
  reviewed_at: string | null; created_at: string | null
}

export interface Assumption {
  id: string; toe_id: string; code: string; description: string | null
  review_status: string; ai_generated: boolean
  reviewed_at: string | null; created_at: string | null
}

export interface OSP {
  id: string; toe_id: string; code: string; description: string | null
  review_status: string; ai_generated: boolean
  reviewed_at: string | null; created_at: string | null
}

export interface STReference {
  id: string; user_id: string; toe_id: string | null
  product_name: string; product_type: string | null
  parse_status: string; parse_error: string | null; is_shared: boolean
  threats_extracted: string | null; objectives_extracted: string | null
  sfr_extracted: string | null; assets_extracted: string | null
  parsed_at: string | null; created_at: string | null
}

export interface CompletenessMetric {
  key: string
  covered: number
  total: number
  percent: number
  status: 'good' | 'attention' | 'weak' | 'not_applicable'
}

export interface CompletenessFindingItem {
  id?: string
  label: string
  detail: string
  importance?: number
  risk_level?: string
  ignored?: boolean
}

export interface CompletenessFinding {
  key: string
  severity: 'high' | 'medium' | 'low'
  count: number
  items: CompletenessFindingItem[]
  overflow: number
}

export interface CompletenessMappingGapSection {
  key: string
  source_type: 'threat' | 'assumption' | 'osp' | 'objective'
  objective_type: 'O' | 'OE'
  covered: number
  total: number
  gaps: CompletenessFindingItem[]
  overflow: number
}

export interface ThreatCompletenessReport {
  summary: {
    score: number
    status: 'good' | 'attention' | 'weak'
    total_findings: number
    high_findings: number
    generated_at: string
    basis_note: string
  }
  basis: {
    asset_count: number
    covered_assets_count: number
    threat_count: number
    confirmed_threat_count: number
    assumption_count: number
    osp_count: number
    objective_count: number
    sfr_count: number
    test_count: number
    reference_threat_count: number
  }
  metrics: CompletenessMetric[]
  mapping_gap_sections: CompletenessMappingGapSection[]
  findings: CompletenessFinding[]
  next_actions: string[]
}

const base = (toeId: string) => `/toes/${toeId}`

export const threatApi = {
  // ── Threats ──
  listThreats: (toeId: string, params?: any) =>
    request.get<any, { code: number; data: Threat[] }>(`${base(toeId)}/threats`, { params }),
  createThreat: (toeId: string, data: any) =>
    request.post<any, { code: number; data: Threat }>(`${base(toeId)}/threats`, data),
  updateThreat: (toeId: string, id: string, data: any) =>
    request.put<any, { code: number; data: Threat }>(`${base(toeId)}/threats/${id}`, data),
  deleteThreat: (toeId: string, id: string) =>
    request.delete(`${base(toeId)}/threats/${id}`),
  confirmThreat: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/threats/${id}/confirm`),
  falsePositiveThreat: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/threats/${id}/false-positive`),
  revertThreat: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/threats/${id}/revert`),
  overrideRisk: (toeId: string, id: string, risk_level: string) =>
    request.put(`${base(toeId)}/threats/${id}/risk-override`, { risk_level }),
  batchConfirm: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { updated: number } }>(`${base(toeId)}/threats/batch-confirm`, { ids }),
  batchFalsePositive: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { updated: number } }>(`${base(toeId)}/threats/batch-false-positive`, { ids }),
  batchDelete: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { deleted: number } }>(`${base(toeId)}/threats/batch-delete`, { ids }),
  aiScan: (toeId: string, mode: 'full' | 'incremental', language: 'zh' | 'en' = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/threats/ai-scan`, { mode, language }),
  importFromDocs: (toeId: string) =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/threats/import-from-docs`, {}),
  getCompletenessReport: (toeId: string) =>
    request.get<any, { code: number; data: ThreatCompletenessReport }>(`${base(toeId)}/threats/completeness-report`),
  toggleWeakCoverageIgnore: (toeId: string, assetId: string) =>
    request.post<any, { code: number; data: { asset_id: string; weak_coverage_ignored: boolean } }>(`${base(toeId)}/assets/${assetId}/toggle-weak-coverage-ignore`, {}),

  // ── Assumptions ──
  listAssumptions: (toeId: string) =>
    request.get<any, { code: number; data: Assumption[] }>(`${base(toeId)}/assumptions`),
  createAssumption: (toeId: string, data: any) =>
    request.post<any, { code: number; data: Assumption }>(`${base(toeId)}/assumptions`, data),
  updateAssumption: (toeId: string, id: string, data: any) =>
    request.put<any, { code: number; data: Assumption }>(`${base(toeId)}/assumptions/${id}`, data),
  deleteAssumption: (toeId: string, id: string) =>
    request.delete(`${base(toeId)}/assumptions/${id}`),
  confirmAssumption: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/assumptions/${id}/confirm`),
  rejectAssumption: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/assumptions/${id}/reject`),
  revertAssumption: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/assumptions/${id}/revert`),
  batchConfirmAssumptions: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { updated: number } }>(`${base(toeId)}/assumptions/batch-confirm`, { ids }),
  batchRejectAssumptions: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { updated: number } }>(`${base(toeId)}/assumptions/batch-reject`, { ids }),
  aiSuggestAssumptions: (toeId: string, language: 'zh' | 'en' = 'en') =>
    request.post<any, { code: number; data: any[] }>(`${base(toeId)}/assumptions/ai-suggest?language=${encodeURIComponent(language)}`),

  // ── OSPs ──
  listOsps: (toeId: string) =>
    request.get<any, { code: number; data: OSP[] }>(`${base(toeId)}/osps`),
  createOsp: (toeId: string, data: any) =>
    request.post<any, { code: number; data: OSP }>(`${base(toeId)}/osps`, data),
  updateOsp: (toeId: string, id: string, data: any) =>
    request.put<any, { code: number; data: OSP }>(`${base(toeId)}/osps/${id}`, data),
  deleteOsp: (toeId: string, id: string) =>
    request.delete(`${base(toeId)}/osps/${id}`),
  confirmOsp: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/osps/${id}/confirm`),
  rejectOsp: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/osps/${id}/reject`),
  revertOsp: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/osps/${id}/revert`),
  batchConfirmOsps: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { updated: number } }>(`${base(toeId)}/osps/batch-confirm`, { ids }),
  batchRejectOsps: (toeId: string, ids: string[]) =>
    request.post<any, { code: number; data: { updated: number } }>(`${base(toeId)}/osps/batch-reject`, { ids }),
  aiSuggestOsps: (toeId: string, language: 'zh' | 'en' = 'en') =>
    request.post<any, { code: number; data: any[] }>(`${base(toeId)}/osps/ai-suggest?language=${encodeURIComponent(language)}`),

  // ── ST reference library ──
  listStRefs: (toeId: string) =>
    request.get<any, { code: number; data: STReference[] }>(`${base(toeId)}/st-references`),
  uploadStRef: (toeId: string, productName: string, file: File, language: string = 'en') => {
    const form = new FormData()
    form.append('file', file)
    return request.post<any, { code: number; data: STReference & { task_id: string } }>(
      `${base(toeId)}/st-references?product_name=${encodeURIComponent(productName)}&language=${encodeURIComponent(language)}`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 }
    )
  },
  deleteStRef: (toeId: string, refId: string) =>
    request.delete(`${base(toeId)}/st-references/${refId}`),
  retryStRef: (toeId: string, refId: string, language: string = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(
      `${base(toeId)}/st-references/${refId}/retry-parse?language=${encodeURIComponent(language)}`
    ),
  shareStRef: (toeId: string, refId: string, is_shared: boolean) =>
    request.patch(`${base(toeId)}/st-references/${refId}/share`, { is_shared }),
}
