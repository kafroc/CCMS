import request from './request'

export interface SecurityObjective {
  id: string; toe_id: string
  code: string; obj_type: string
  description: string | null; rationale: string | null
  review_status: string; ai_generated: boolean
  reviewed_at: string | null; created_at: string | null
}

export interface SFRLibraryItem {
  id: string
  sfr_class: string; sfr_class_name: string
  sfr_family: string; sfr_family_name: string
  sfr_component: string; sfr_component_name: string
  description: string | null; element_text: string | null
  dependencies: string | null; cc_version: string
}

export interface SFRLibraryImportResult {
  imported: number
  updated: number
  items: SFRLibraryItem[]
  errors: Array<{
    row: number
    sfr_id?: string | null
    reason: string
  }>
}

export interface SFRInstance {
  id: string; toe_id: string
  sfr_library_id: string | null; sfr_id: string
  sfr_name?: string | null
  sfr_detail?: string | null
  dependency?: string | null
  source: string; customization_note: string | null
  review_status: string; ai_rationale: string | null
  dependency_warning: string | null
  reviewed_at: string | null; created_at: string | null
  library?: SFRLibraryItem | null
  objective_ids?: string[]
  linked_objectives?: Array<{
    id: string
    code: string
    obj_type: string
    mapping_rationale?: string | null
  }>
  linked_dependency_sfrs?: Array<{
    id: string
    sfr_id: string
    sfr_name?: string | null
  }>
  linked_tests?: Array<{
    id: string
    case_number: string | null
    title: string
    review_status: string
  }>
}

export interface SFRAICompletionResult {
  sfr_id: string
  sfr_name?: string | null
  sfr_detail?: string | null
  dependency?: string | null
  suggested_objective_ids: string[]
  suggested_test_ids: string[]
  available_objectives: Array<{
    id: string
    code: string
    obj_type: string
  }>
  available_tests: Array<{
    id: string
    title: string
  }>
}

export interface SFRDependencyFillResult {
  created_count: number
  created_sfrs: Array<{
    id: string
    sfr_id: string
  }>
  linked_objective_mappings: number
  dependency_state: {
    checked: number
    updated: number
  }
}

export interface ObjectiveSources {
  threat_ids: string[]
  assumption_ids: string[]
  osp_ids: string[]
}

export interface SecurityCompletenessMetric {
  key: string
  covered: number
  total: number
  percent: number
  status: 'good' | 'attention' | 'weak' | 'not_applicable'
}

export interface SecurityCompletenessFindingItem {
  id?: string
  label: string
  detail: string
}

export interface SecurityCompletenessFinding {
  key: string
  severity: 'high' | 'medium' | 'low'
  count: number
  items: SecurityCompletenessFindingItem[]
  overflow: number
}

export interface SecurityCompletenessMappingGapSection {
  key: string
  source_type: 'objective' | 'sfr'
  objective_type: 'O' | 'OE'
  covered: number
  total: number
  gaps: SecurityCompletenessFindingItem[]
  overflow: number
}

export interface SecurityCompletenessReport {
  summary: {
    score: number
    status: 'good' | 'attention' | 'weak'
    total_findings: number
    high_findings: number
    generated_at: string
    basis_note: string
  }
  basis: {
    covered_security_problem_count: number
    security_problem_count: number
    objective_count: number
    sfr_count: number
    o_objective_count: number
    oe_objective_count: number
  }
  metrics: SecurityCompletenessMetric[]
  mapping_gap_sections: SecurityCompletenessMappingGapSection[]
  findings: SecurityCompletenessFinding[]
  next_actions: string[]
}

const base = (toeId: string) => `/toes/${toeId}`

export const securityApi = {
  // Objectives
  listObjectives: (toeId: string, params?: any) =>
    request.get<any, { code: number; data: SecurityObjective[] }>(`${base(toeId)}/objectives`, { params }),
  createObjective: (toeId: string, data: any) =>
    request.post<any, { code: number; data: SecurityObjective }>(`${base(toeId)}/objectives`, data),
  updateObjective: (toeId: string, id: string, data: any) =>
    request.put<any, { code: number; data: SecurityObjective }>(`${base(toeId)}/objectives/${id}`, data),
  deleteObjective: (toeId: string, id: string) =>
    request.delete(`${base(toeId)}/objectives/${id}`),
  confirmObjective: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/objectives/${id}/confirm`),
  rejectObjective: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/objectives/${id}/reject`),
  revertObjective: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/objectives/${id}/revert`),
  aiGenerateObjectives: (toeId: string, mode: string, language: 'zh' | 'en' = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/objectives/ai-generate`, { mode, language }),
  aiSuggestObjectives: (toeId: string) =>
    request.post<any, { code: number; data: any[] }>(`${base(toeId)}/objectives/ai-suggest`, {}),
  importObjectivesFromDocs: (toeId: string) =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/objectives/import-from-docs`, {}),
  getCompletenessReport: (toeId: string) =>
    request.get<any, { code: number; data: SecurityCompletenessReport }>(`${base(toeId)}/security/completeness-report`),

  // Source mappings
  listObjectiveSources: (toeId: string, objectiveId: string) =>
    request.get<any, { code: number; data: ObjectiveSources }>(`${base(toeId)}/objectives/${objectiveId}/sources`),
  addSourceMapping: (toeId: string, objectiveId: string, source_type: string, source_id: string) =>
    request.post(`${base(toeId)}/objectives/${objectiveId}/map-source`, { source_type, source_id }),
  removeSourceMapping: (toeId: string, objectiveId: string, source_type: string, source_id: string) =>
    request.delete(`${base(toeId)}/objectives/${objectiveId}/map-source/${source_type}/${source_id}`),

  // SFR Library
  listSFRLibrary: (params?: any) =>
    request.get<any, { code: number; data: { items: SFRLibraryItem[]; total: number; classes: any[] } }>('/sfr-library', { params }),
  getSFRLibraryDetail: (sfr_component: string) =>
    request.get<any, { code: number; data: SFRLibraryItem }>(`/sfr-library/${sfr_component}`),
  createSFRLibrary: (data: { sfr_component: string; sfr_component_name?: string | null; description?: string | null; dependencies?: string | null }) =>
    request.post<any, { code: number; data: SFRLibraryItem }>(`/sfr-library`, data),
  updateSFRLibrary: (id: string, data: { sfr_component: string; sfr_component_name?: string | null; description?: string | null; dependencies?: string | null }) =>
    request.put<any, { code: number; data: SFRLibraryItem }>(`/sfr-library/${id}`, data),
  deleteSFRLibrary: (id: string) =>
    request.delete(`/sfr-library/${id}`),
  batchDeleteSFRLibrary: (ids: string[]) =>
    request.post<any, { code: number; data: { deleted: number } }>(`/sfr-library/batch-delete`, { ids }),
  importSFRLibraryFromDoc: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post<any, { code: number; data: SFRLibraryImportResult }>(`/sfr-library/import-from-doc`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000,
    })
  },

  // TOE SFRs
  listSFRs: (toeId: string, params?: any) =>
    request.get<any, { code: number; data: SFRInstance[] }>(`${base(toeId)}/sfrs`, { params }),
  createSFR: (toeId: string, data: any) =>
    request.post<any, { code: number; data: SFRInstance }>(`${base(toeId)}/sfrs`, data),
  updateSFR: (toeId: string, id: string, data: any) =>
    request.put<any, { code: number; data: SFRInstance }>(`${base(toeId)}/sfrs/${id}`, data),
  deleteSFR: (toeId: string, id: string) =>
    request.delete(`${base(toeId)}/sfrs/${id}`),
  confirmSFR: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/sfrs/${id}/confirm`),
  rejectSFR: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/sfrs/${id}/reject`),
  revertSFR: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/sfrs/${id}/revert`),
  aiMatchSFRs: (toeId: string, mode: string, language: string = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/sfrs/ai-match`, { mode, language }),
  stppValidateSFRs: (toeId: string, language: string = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/sfrs/st-pp-validate`, { language }),
  aiCompleteSFR: (toeId: string, data: { sfr_id: string; current_objective_ids?: string[]; current_test_ids?: string[] }) =>
    request.post<any, { code: number; data: SFRAICompletionResult }>(`${base(toeId)}/sfrs/ai-complete`, data),
  fillSFRDependencies: (toeId: string, sfrId: string) =>
    request.post<any, { code: number; data: SFRDependencyFillResult }>(`${base(toeId)}/sfrs/${sfrId}/fill-dependencies`, {}),
  autoManageSFRs: (toeId: string) =>
    request.post<any, { code: number; data: { checked: number; updated: number } }>(`${base(toeId)}/sfrs/auto-manage`, {}),

  // Objective ↔ SFR mappings
  listObjectiveSFRs: (toeId: string, objectiveId: string) =>
    request.get<any, { code: number; data: any[] }>(`${base(toeId)}/objectives/${objectiveId}/sfrs`),
  addObjectiveSFR: (toeId: string, objectiveId: string, sfr_id: string, mapping_rationale?: string) =>
    request.post(`${base(toeId)}/objectives/${objectiveId}/map-sfr`, { sfr_id, mapping_rationale }),
  removeObjectiveSFR: (toeId: string, objectiveId: string, sfr_id: string) =>
    request.delete(`${base(toeId)}/objectives/${objectiveId}/map-sfr/${sfr_id}`),
}
