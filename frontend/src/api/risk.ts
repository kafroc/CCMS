import request from './request'

export interface RiskAssessment {
  id: string; toe_id: string; threat_id: string
  residual_risk: string; mitigation_notes: string | null
  assessor: string | null; assessed_at: string
}

export interface SecurityProblem {
  type: 'threat' | 'assumption' | 'osp'
  id: string
  code: string
  risk_level?: string  // Only for threats
  review_status: string
  objectives: number
  sfrs: number
  tests: number
  confirmed_tests: number
  chain_status: string
}

export interface RiskDashboard {
  risk_distribution: Record<string, number>
  status_distribution: Record<string, number>
  residual_distribution: Record<string, number>
  total_threats: number
  total_assumptions: number
  total_osps: number
  risk_score: number
  overall_risk_level: string
  ai_summary: string | null
  security_problems: SecurityProblem[]
  // Keep threats for backward compatibility
  threats?: SecurityProblem[]
}

export interface ChainTreeNode {
  id: string
  label: string
  type: string
  risk_level?: string
  review_status?: string
  obj_type?: string
}

export interface ChainTreeEdge {
  from: string
  to: string
  type: string
}

export interface ChainTreeLayer {
  key: string
  nodes: ChainTreeNode[]
}

export interface ChainTreeData {
  layers: ChainTreeLayer[]
  edges: ChainTreeEdge[]
}

const base = (toeId: string) => `/toes/${toeId}`

export const riskApi = {
  listAssessments: (toeId: string) =>
    request.get<any, { code: number; data: RiskAssessment[] }>(`${base(toeId)}/risk-assessments`),
  upsertAssessment: (toeId: string, threatId: string, data: any) =>
    request.put<any, { code: number; data: RiskAssessment }>(`${base(toeId)}/risk-assessments/${threatId}`, data),
  getDashboard: (toeId: string) =>
    request.get<any, { code: number; data: RiskDashboard }>(`${base(toeId)}/risk-dashboard`),
  generateSummary: (toeId: string, language: 'zh' | 'en' = 'en') =>
    request.post<any, { code: number; data: { task_id: string } }>(`${base(toeId)}/risk-summary/generate`, { language }),
  getBlindSpots: (toeId: string) =>
    request.get<any, { code: number; data: RiskBlindSpots }>(`${base(toeId)}/risk-blind-spots`),
  getChainTree: (toeId: string) =>
    request.get<any, { code: number; data: ChainTreeData }>(`${base(toeId)}/assurance-chain-tree`),
}

export interface BlindSpotIndicator {
  level: 'critical' | 'high' | 'medium' | 'low'
  message: string
  detail?: any
}

export interface BlindSpotDimension {
  indicators: BlindSpotIndicator[]
  stats: Record<string, any>
}

export interface RiskBlindSpots {
  overall_confidence: 'very_high' | 'high' | 'medium' | 'low'
  dimensions: {
    asset_identification: BlindSpotDimension
    threat_identification: BlindSpotDimension
    sfr_adequacy: BlindSpotDimension
    test_depth: BlindSpotDimension
  }
}

