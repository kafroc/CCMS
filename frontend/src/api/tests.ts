import request from './request'

export interface TestCase {
  id: string; toe_id: string
  case_number: string | null
  primary_sfr_id: string; primary_sfr_label?: string
  related_sfr_ids: string | null
  related_sfr_labels?: string[]
  test_type: string; title: string
  objective: string | null
  test_target: string | null
  test_scenario: string | null
  precondition: string | null
  test_steps: string | null; expected_result: string | null
  review_status: string; ai_generated: boolean
  reviewed_at: string | null; created_at: string | null
}

export interface TestCompletenessMetric {
  key: string
  covered: number
  total: number
  percent: number
  status: 'good' | 'attention' | 'weak' | 'not_applicable'
}

export interface TestCompletenessFindingItem {
  id?: string
  label: string
  detail: string
}

export interface TestCompletenessFinding {
  key: string
  severity: 'high' | 'medium' | 'low'
  count: number
  items: TestCompletenessFindingItem[]
  overflow: number
}

export interface TestCompletenessMappingGapSection {
  key: string
  source_type: 'sfr'
  objective_type: 'O' | 'OE'
  covered: number
  total: number
  gaps: TestCompletenessFindingItem[]
  overflow: number
}

export interface TestCompletenessReport {
  summary: {
    score: number
    status: 'good' | 'attention' | 'weak'
    total_findings: number
    high_findings: number
    generated_at: string
    basis_note: string
  }
  basis: {
    sfr_count: number
    test_count: number
    confirmed_test_count: number
  }
  metrics: TestCompletenessMetric[]
  mapping_gap_sections: TestCompletenessMappingGapSection[]
  findings: TestCompletenessFinding[]
  next_actions: string[]
}

const base = (toeId: string) => `/toes/${toeId}`

export const testApi = {
  list: (toeId: string, params?: any) =>
    request.get<any, { code: number; data: TestCase[] }>(`${base(toeId)}/test-cases`, { params }),
  create: (toeId: string, data: any) =>
    request.post<any, { code: number; data: TestCase }>(`${base(toeId)}/test-cases`, data),
  update: (toeId: string, id: string, data: any) =>
    request.put<any, { code: number; data: TestCase }>(`${base(toeId)}/test-cases/${id}`, data),
  delete: (toeId: string, id: string) =>
    request.delete(`${base(toeId)}/test-cases/${id}`),
  confirm: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/test-cases/${id}/confirm`),
  reject: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/test-cases/${id}/reject`),
  revert: (toeId: string, id: string) =>
    request.post(`${base(toeId)}/test-cases/${id}/revert`),
  aiGenerate: (toeId: string, sfr_ids?: string[], language: 'zh' | 'en' = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/test-cases/ai-generate`, { sfr_ids, language }),
  batchConfirm: (toeId: string, ids: string[]) =>
    request.post(`${base(toeId)}/test-cases/batch-confirm`, { ids }),
  batchDelete: (toeId: string, ids: string[]) =>
    request.post(`${base(toeId)}/test-cases/batch-delete`, { ids }),
  getCompletenessReport: (toeId: string) =>
    request.get<any, { code: number; data: TestCompletenessReport }>(`${base(toeId)}/test-cases/completeness-report`),
}
