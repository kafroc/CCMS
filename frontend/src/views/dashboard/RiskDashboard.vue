<template>
  <div class="risk-dashboard">
    <n-page-header :title="t.risk.title" :subtitle="t.risk.subtitle">
      <template #extra>
        <n-space>
          <n-select
            v-model:value="selectedToeId"
            :options="toeOptions"
            :placeholder="t.threat.selectToe"
            style="width: 260px"
            @update:value="onToeChange"
          />
          <n-button @click="loadAll" :loading="loading">{{ t.common.refresh }}</n-button>
        </n-space>
      </template>
    </n-page-header>

    <div v-if="!selectedToeId" style="margin-top: 80px; text-align: center">
      <n-empty :description="t.threat.selectToeTip" />
    </div>

    <template v-else>
      <n-spin :show="loading" style="min-height: 200px">
        <template v-if="dashboard">
          <!-- ========== Section 1: Executive Summary ========== -->
          <div class="section executive-summary">
            <div class="summary-row">
              <!-- Assurance Maturity Gauge -->
              <div class="summary-col-gauge">
                <n-card size="small" class="summary-card score-card">
                  <template #header>
                    <n-space align="center" :size="6" :wrap="false">
                      <span>{{ t.risk.assuranceMaturity }}</span>
                      <n-tooltip trigger="hover" :width="460" :theme-overrides="{ color: '#f5f5f5', textColor: '#303133', boxShadow: '0 2px 12px rgba(0,0,0,0.15)' }">
                        <template #trigger>
                          <n-tag size="tiny" round :bordered="false" type="info">?</n-tag>
                        </template>
                        <div class="metric-tooltip">
                          <div class="metric-tooltip-title">{{ t.risk.assuranceMaturity }}</div>
                          <div class="metric-tooltip-label">{{ t.risk.calculationLabel }}</div>
                          <div class="metric-tooltip-text">{{ t.risk.assuranceFormula }}</div>
                          <div class="metric-tooltip-tags">
                            <n-tag v-for="item in assuranceComponents" :key="item.label" size="small" round>
                              {{ item.label }} {{ item.value }}%
                            </n-tag>
                          </div>
                          <div class="metric-tooltip-label">{{ t.risk.improvementLabel }}</div>
                          <ul class="metric-tooltip-list">
                            <li v-for="(tip, index) in assuranceTips" :key="`assurance-${index}`">{{ tip }}</li>
                          </ul>
                        </div>
                      </n-tooltip>
                    </n-space>
                  </template>
                  <div class="score-gauge">
                    <div class="gauge-ring" :style="gaugeStyle">
                      <div class="gauge-inner">
                        <span class="gauge-value">{{ securityScore }}</span>
                        <span class="gauge-label">/ 100</span>
                      </div>
                    </div>
                    <n-tooltip trigger="hover">
                      <template #trigger>
                        <n-tag :type="overallTagType" size="small" round>{{ overallLevelLabel }}</n-tag>
                      </template>
                      {{ t.risk.maturityCaveat }}
                    </n-tooltip>
                  </div>
                </n-card>
              </div>
              <!-- CC Assurance Chain (pipeline) -->
              <div class="summary-col-chain">
                <n-card size="small" class="summary-card chain-pipeline-card">
                  <template #header>
                    <n-space align="center" :size="8">
                      <span>{{ t.risk.assuranceChain }}</span>
                      <n-tooltip
                        trigger="hover"
                        :width="320"
                        :theme-overrides="{ color: '#f5f5f5', textColor: '#303133', boxShadow: '0 2px 12px rgba(0,0,0,0.15)' }"
                      >
                        <template #trigger>
                          <n-tag size="tiny" round :bordered="false" type="info">?</n-tag>
                        </template>
                        {{ t.risk.chainCaveat }}
                      </n-tooltip>
                    </n-space>
                  </template>
                  <div class="chain-pipeline">
                    <div
                      v-for="(stage, idx) in chainStages"
                      :key="stage.key"
                      class="chain-stage"
                    >
                      <div class="stage-node" :class="stage.statusClass">
                        <div class="stage-icon">{{ stage.icon }}</div>
                        <div class="stage-name">{{ stage.name }}</div>
                        <div class="stage-count">{{ stage.count }}</div>
                        <div class="stage-bar-wrap">
                          <div class="stage-bar" :style="{ width: stage.percent + '%', backgroundColor: stage.color }"></div>
                        </div>
                        <div class="stage-percent" :style="{ color: stage.color }">{{ stage.percent }}%</div>
                      </div>
                      <div v-if="idx < chainStages.length - 1" class="chain-arrow">
                        <svg width="28" height="20" viewBox="0 0 28 20"><path d="M0 10 L20 10 M14 4 L22 10 L14 16" stroke="#c0c4cc" stroke-width="2" fill="none"/></svg>
                      </div>
                    </div>
                  </div>
                  <div class="chain-legend">
                    <span class="legend-item"><span class="legend-dot" style="background:#18a058"></span>{{ t.risk.chainGood }}</span>
                    <span class="legend-item"><span class="legend-dot" style="background:#f0a020"></span>{{ t.risk.chainAttention }}</span>
                    <span class="legend-item"><span class="legend-dot" style="background:#d03050"></span>{{ t.risk.chainWeak }}</span>
                  </div>
                </n-card>
              </div>
            </div>
          </div>

          <!-- ========== Section 2: Assurance Tree ========== -->
          <div class="section">
            <n-card size="small">
              <template #header>
                <n-space align="center" :size="8">
                  <span>{{ t.risk.assuranceTree }}</span>
                  <n-tooltip
                    trigger="hover"
                    :width="320"
                    :theme-overrides="{ color: '#f5f5f5', textColor: '#303133', boxShadow: '0 2px 12px rgba(0,0,0,0.15)' }"
                  >
                    <template #trigger>
                      <n-tag size="tiny" round :bordered="false" type="info">?</n-tag>
                    </template>
                    {{ t.risk.treeClickHint }}
                  </n-tooltip>
                </n-space>
              </template>
              <AssuranceChainTree
                v-if="chainTreeData"
                :data="chainTreeData"
                :labels="treeLayerLabels"
              />
              <n-empty v-else :description="t.common.noData" />
            </n-card>
          </div>

          <!-- ========== Section 2: Risk Blind Spots ========== -->
          <div class="section">
            <n-card size="small">
              <template #header>
                <n-space align="center" :size="8">
                  <span>{{ t.risk.blindSpots }}</span>
                  <n-tag v-if="blindSpots" :type="confidenceTagType" size="small" round>
                    {{ t.risk.confidence }}: {{ confidenceLabel }}
                  </n-tag>
                  <n-tooltip
                    trigger="hover"
                    :width="480"
                    :theme-overrides="{ color: '#f5f5f5', textColor: '#303133', boxShadow: '0 2px 12px rgba(0,0,0,0.15)' }"
                  >
                    <template #trigger>
                      <n-tag size="tiny" round :bordered="false" type="info">?</n-tag>
                    </template>
                    <div style="font-size: 13px; line-height: 1.7">
                      <div style="margin-bottom: 8px">{{ t.risk.blindSpotsExplain }}</div>
                      <div style="font-weight: 600; margin-bottom: 4px">{{ t.risk.bsTooltipLogicTitle }}</div>
                      <div v-for="dim in bsTooltipDims" :key="dim.key" style="margin-bottom: 6px">
                        <span style="font-weight: 600">{{ dim.icon }} {{ dim.title }}：</span>
                        <span>{{ dim.desc }}</span>
                      </div>
                    </div>
                  </n-tooltip>
                </n-space>
              </template>

              <!-- Warning banner -->
              <div class="bs-warning-banner">
                <span class="bs-warning-icon">⚠️</span>
                <span class="bs-warning-text">{{ t.risk.bsWarning }}</span>
              </div>

              <!-- Identified Risks -->
              <div v-if="allBlindSpotIndicators.length > 0" class="bs-risk-list">
                <div class="bs-risk-title">{{ t.risk.bsIdentifiedRisks }}</div>
                <div
                  v-for="(item, i) in allBlindSpotIndicators"
                  :key="i"
                  class="bs-risk-item"
                >
                  <span class="bs-dot" :class="'dot-' + item.level"></span>
                  <span class="bs-risk-dim">{{ item.icon }}</span>
                  <span class="bs-risk-msg">{{ item.message }}</span>
                </div>
              </div>
              <div v-else-if="blindSpots" class="bs-all-ok">
                <n-tag type="success" size="small" round>✓ {{ t.risk.bsOk }}</n-tag>
              </div>

            </n-card>
          </div>

          <!-- ========== Section 4: Charts Row ========== -->
          <div class="section">
            <n-grid :cols="3" :x-gap="16" responsive="screen" cols-s="1">
              <n-gi>
                <n-card :title="t.risk.riskDistribution" size="small" class="chart-card">
                  <v-chart :key="`risk-dist-${selectedToeId}`" :option="riskDistOption" :update-options="chartUpdateOptions" :autoresize="true" style="height: 240px" />
                </n-card>
              </n-gi>
              <n-gi>
                <n-card :title="t.risk.residualStatus" size="small" class="chart-card">
                  <v-chart :key="`residual-dist-${selectedToeId}`" :option="residualDistOption" :update-options="chartUpdateOptions" :autoresize="true" style="height: 240px" />
                </n-card>
              </n-gi>
              <n-gi>
                <n-card :title="t.risk.completenessRadar" size="small" class="chart-card">
                  <v-chart :key="`completeness-radar-${selectedToeId}`" :option="radarOption" :update-options="chartUpdateOptions" :autoresize="true" style="height: 240px" />
                </n-card>
              </n-gi>
            </n-grid>
          </div>

          <!-- ========== Section 5: Key Findings ========== -->
          <div class="section" v-if="keyFindings.length > 0">
            <n-card :title="t.risk.keyFindings" size="small">
              <div class="findings-list">
                <div
                  v-for="(f, i) in keyFindings"
                  :key="i"
                  class="finding-item"
                  :class="'finding-' + f.severity"
                >
                  <span class="finding-badge" :class="'badge-' + f.severity">
                    {{ f.severity === 'high' ? '!' : f.severity === 'medium' ? '~' : 'i' }}
                  </span>
                  <span class="finding-text">{{ f.text }}</span>
                  <n-tag :type="f.severity === 'high' ? 'error' : f.severity === 'medium' ? 'warning' : 'info'" size="tiny" round>
                    {{ f.count }}
                  </n-tag>
                </div>
              </div>
            </n-card>
          </div>

          <!-- ========== Section 6: AI Summary ========== -->
          <div class="section" v-if="dashboard.ai_summary">
            <n-card :title="t.risk.aiSummary" size="small">
              <n-text style="white-space: pre-wrap; line-height: 1.6">{{ dashboard.ai_summary }}</n-text>
            </n-card>
          </div>

          <!-- ========== Section 7: Security Problem Assurance Chain ========== -->
          <div class="section">
            <n-card :title="t.risk.securityProblemChain" size="small">
              <div class="security-problem-table-wrap">
                <n-data-table
                  :columns="problemColumns"
                  :data="dashboard.security_problems || dashboard.threats"
                  :pagination="securityProblemPagination"
                  :bordered="false"
                  size="small"
                  :row-class-name="problemRowClass"
                  :max-height="securityProblemTableHeight"
                />
              </div>
            </n-card>
          </div>
        </template>
      </n-spin>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, h } from 'vue'
import { useMessage, NTag, type DataTableColumn } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { toeApi } from '@/api/toes'
import { riskApi, type RiskBlindSpots, type BlindSpotIndicator, type ChainTreeData } from '@/api/risk'
import { threatApi } from '@/api/threats'
import { securityApi } from '@/api/security'
import { testApi } from '@/api/tests'
import { useLocaleStore } from '@/stores/locale'
import { useToeSelectionStore } from '@/stores/toeSelection'
import { getMessages } from '@/locales'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, RadarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, RadarComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import AssuranceChainTree from '@/components/common/AssuranceChainTree.vue'

use([CanvasRenderer, PieChart, RadarChart, TitleComponent, TooltipComponent, LegendComponent, RadarComponent])

const localeStore = useLocaleStore()
const toeSelectionStore = useToeSelectionStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const route = useRoute()
const router = useRouter()

const selectedToeId = ref<string | null>(null)
const toeOptions = ref<{ label: string; value: string }[]>([])
const dashboard = ref<any>(null)
const threatReport = ref<any>(null)
const securityReport = ref<any>(null)
const testReport = ref<any>(null)
const blindSpots = ref<RiskBlindSpots | null>(null)
const chainTreeData = ref<ChainTreeData | null>(null)
const loading = ref(false)
const chartUpdateOptions = { notMerge: true, lazyUpdate: true }
const securityProblemTableHeight = 620
const securityProblemPagination = { pageSize: 15 }

function findFindingCount(report: any, key: string): number {
  const finding = report?.findings?.find((item: any) => item.key === key)
  return finding?.count ?? 0
}

function uniqueStrings(items: string[]): string[] {
  return Array.from(new Set(items.filter(Boolean)))
}

function translateThreatAction(action: string): string {
  const map: Record<string, string> = {
    action_cover_uncovered_assets: t.value.threat.actionCoverUncoveredAssets,
    action_threat_objectives: t.value.threat.actionThreatObjectives,
    action_assumption_objectives: t.value.threat.actionAssumptionObjectives,
    action_osp_objectives: t.value.threat.actionOspObjectives,
    action_objectives_sources: t.value.threat.actionObjectivesSources,
    action_no_gaps: t.value.threat.actionNoGaps,
  }
  return map[action] || action
}

function translateSecurityAction(action: string): string {
  const map: Record<string, string> = {
    action_sfr_objectives: t.value.threat.actionSfrObjectives,
    action_sfr_dependencies: t.value.security.actionSfrDependencies,
    action_redundant_sfrs: t.value.threat.actionRedundantSfrs,
    action_no_gaps: t.value.threat.actionNoGaps,
  }
  return map[action] || action
}

// ── TOE loading ──
async function loadToes() {
  try {
    const res = await toeApi.list()
    toeOptions.value = res.data.map((t: any) => ({ label: t.name, value: t.id }))
    const routeToeId = typeof route.query.toeId === 'string' ? route.query.toeId : null
    const storedToeId = toeSelectionStore.selectedToeId
    const initialToeId = routeToeId && toeOptions.value.some(item => item.value === routeToeId)
      ? routeToeId
      : storedToeId && toeOptions.value.some(item => item.value === storedToeId)
        ? storedToeId
        : toeOptions.value[0]?.value
    if (initialToeId && !selectedToeId.value) {
      selectedToeId.value = initialToeId
      toeSelectionStore.setSelectedToeId(initialToeId)
      loadAll()
    }
  } catch (e: any) {
    message.error(e.message)
  }
}

// ── Load all data in parallel ──
async function loadAll() {
  if (!selectedToeId.value) return
  loading.value = true
  try {
    const toeId = selectedToeId.value
    const [riskRes, threatRes, secRes, testRes, bsRes, treeRes] = await Promise.all([
      riskApi.getDashboard(toeId),
      threatApi.getCompletenessReport(toeId).catch(() => null),
      securityApi.getCompletenessReport(toeId).catch(() => null),
      testApi.getCompletenessReport(toeId).catch(() => null),
      riskApi.getBlindSpots(toeId).catch(() => null),
      riskApi.getChainTree(toeId).catch(() => null),
    ])
    dashboard.value = riskRes.data
    threatReport.value = threatRes?.data ?? null
    securityReport.value = secRes?.data ?? null
    testReport.value = testRes?.data ?? null
    blindSpots.value = bsRes?.data ?? null
    chainTreeData.value = treeRes?.data ?? null
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function onToeChange() {
  toeSelectionStore.setSelectedToeId(selectedToeId.value)
  router.replace({ name: 'Risk', query: { toeId: selectedToeId.value || undefined } })
  loadAll()
}

// ── Computed: Assurance Maturity Score (weighted average) ──
const securityScore = computed(() => {
  if (!dashboard.value) return 0
  const scores: number[] = []
  const weights: number[] = []
  if (threatReport.value?.summary?.score != null) {
    scores.push(threatReport.value.summary.score); weights.push(25)
  }
  if (securityReport.value?.summary?.score != null) {
    scores.push(securityReport.value.summary.score); weights.push(25)
  }
  if (testReport.value?.summary?.score != null) {
    scores.push(testReport.value.summary.score); weights.push(25)
  }
  scores.push(mitigationRate.value); weights.push(25)
  if (weights.length === 0) return 0
  const totalWeight = weights.reduce((a, b) => a + b, 0)
  const weightedSum = scores.reduce((sum, s, i) => sum + s * weights[i], 0)
  return Math.round(weightedSum / totalWeight)
})

const overallLevelLabel = computed(() => {
  const s = securityScore.value
  if (s >= 85) return t.value.risk.levelSecure
  if (s >= 60) return t.value.risk.levelModerate
  if (s >= 30) return t.value.risk.levelAtRisk
  return t.value.risk.levelCritical
})

const overallTagType = computed<'success' | 'warning' | 'error' | 'default'>(() => {
  const s = securityScore.value
  if (s >= 85) return 'success'
  if (s >= 60) return 'warning'
  return 'error'
})

const gaugeStyle = computed(() => {
  const s = securityScore.value
  const color = s >= 85 ? '#18a058' : s >= 60 ? '#f0a020' : '#d03050'
  const deg = (s / 100) * 360
  return { background: `conic-gradient(${color} ${deg}deg, #e8e8e8 ${deg}deg)` }
})

// ── Mitigation Rate ──
const mitigationRate = computed(() => {
  if (!dashboard.value) return 0
  const rd = dashboard.value.residual_distribution
  const total = Object.values(rd).reduce((a: number, b: any) => a + b, 0) as number
  if (total === 0) return 100
  const mitigated = (rd.mitigated ?? 0) + (rd.transferred ?? 0) + (rd.avoided ?? 0)
  return Math.round((mitigated / total) * 100)
})

const threatCompletenessScore = computed(() => threatReport.value?.summary?.score ?? 0)
const securityCompletenessScore = computed(() => securityReport.value?.summary?.score ?? 0)
const testCompletenessScore = computed(() => testReport.value?.summary?.score ?? 0)

const assuranceComponents = computed(() => [
  { label: t.value.risk.componentThreatCompleteness, value: threatCompletenessScore.value },
  { label: t.value.risk.componentSecurityCompleteness, value: securityCompletenessScore.value },
  { label: t.value.risk.componentTestCompleteness, value: testCompletenessScore.value },
  { label: t.value.risk.componentMitigationRate, value: mitigationRate.value },
])

const assuranceTips = computed(() => {
  const tips: string[] = []

  if (threatCompletenessScore.value < 85) {
    for (const action of threatReport.value?.next_actions ?? []) {
      tips.push(translateThreatAction(action))
    }
  }

  if (securityCompletenessScore.value < 85) {
    for (const action of securityReport.value?.next_actions ?? []) {
      tips.push(translateSecurityAction(action))
    }
  }

  if (testCompletenessScore.value < 85) {
    if (findFindingCount(testReport.value, 'sfrs_without_tests') > 0) {
      tips.push(t.value.risk.tipAddTestsForSfrs)
    }
    if (findFindingCount(testReport.value, 'sfrs_without_confirmed_tests') > 0) {
      tips.push(t.value.risk.tipConfirmTests)
    }
    if (findFindingCount(testReport.value, 'tests_without_steps') > 0) {
      tips.push(t.value.risk.tipCompleteTestSteps)
    }
  }

  if (mitigationRate.value < 85) {
    tips.push(t.value.risk.tipImproveMitigationWithAssessments)
  }

  const deduped = uniqueStrings(tips).filter(item => item !== t.value.threat.actionNoGaps)
  return deduped.length > 0 ? deduped.slice(0, 4) : [t.value.risk.tipNoImmediateGap]
})

const mitigationBreakdown = computed(() => {
  const residual = dashboard.value?.residual_distribution ?? {}
  return [
    { label: t.value.risk.resMitigated, value: residual.mitigated ?? 0, type: 'success' as const },
    { label: t.value.risk.resTransferred, value: residual.transferred ?? 0, type: 'info' as const },
    { label: t.value.risk.resAvoided, value: residual.avoided ?? 0, type: 'success' as const },
    { label: t.value.risk.resAccepted, value: residual.accepted ?? 0, type: 'warning' as const },
    { label: t.value.risk.resUnassessed, value: residual.unassessed ?? 0, type: 'default' as const },
  ]
})

const pendingThreatCount = computed(() => {
  const problems = dashboard.value?.security_problems ?? []
  return problems.filter((item: any) => item.type === 'threat' && item.review_status === 'pending').length
})

const mitigationTips = computed(() => {
  const residual = dashboard.value?.residual_distribution ?? {}
  const tips: string[] = []

  if ((dashboard.value?.total_threats ?? 0) === 0) {
    return [t.value.risk.tipNoThreatsYet]
  }

  if ((residual.unassessed ?? 0) > 0) {
    tips.push(t.value.risk.tipAssessResidual.replace('{count}', String(residual.unassessed ?? 0)))
  }
  if ((residual.accepted ?? 0) > 0) {
    tips.push(t.value.risk.tipReduceAccepted.replace('{count}', String(residual.accepted ?? 0)))
  }
  if (pendingThreatCount.value > 0) {
    tips.push(t.value.risk.tipConfirmPendingThreats.replace('{count}', String(pendingThreatCount.value)))
  }

  const deduped = uniqueStrings(tips)
  return deduped.length > 0 ? deduped.slice(0, 4) : [t.value.risk.tipAllMitigated]
})

// ── Test Coverage ──
const testCoverage = computed(() => {
  if (!testReport.value?.metrics) return 0
  const m = testReport.value.metrics.find((m: any) => m.key === 'sfr_test_coverage')
  return m?.percent ?? 0
})

// ── Tree Layer Labels ──
const treeLayerLabels = computed<Record<string, string>>(() => ({
  asset: t.value.risk.treeLayerAsset,
  problem: t.value.risk.treeLayerProblem,
  objective: t.value.risk.treeLayerObjective,
  sfr: t.value.risk.treeLayerSfr,
  test: t.value.risk.treeLayerTest,
}))

// ── CC Assurance Chain ──
const chainStages = computed(() => {
  const tb = threatReport.value?.basis
  const sb = securityReport.value?.basis
  const testb = testReport.value?.basis

  const assetMetric = threatReport.value?.metrics?.find((m: any) => m.key === 'asset_coverage')
  const assetPercent = assetMetric?.percent ?? (tb?.asset_count > 0 ? Math.round((tb?.covered_assets_count / tb?.asset_count) * 100) : 0)
  const spdPercent = threatReport.value?.summary?.score ?? 0
  const objMetric = securityReport.value?.metrics?.find((m: any) => m.key === 'security_problem_objective_coverage')
  const objPercent = objMetric?.percent ?? 0
  const sfrMetric = securityReport.value?.metrics?.find((m: any) => m.key === 'objective_sfr_coverage')
  const sfrPercent = sfrMetric?.percent ?? 0
  const testPercent = testCoverage.value

  function stageColor(p: number) { return p >= 85 ? '#18a058' : p >= 60 ? '#f0a020' : '#d03050' }
  function statusClass(p: number) { return p >= 85 ? 'stage-good' : p >= 60 ? 'stage-attention' : 'stage-weak' }

  return [
    { key: 'assets', icon: '\u{1F4E6}', name: t.value.risk.chainAssets, count: tb?.asset_count ?? 0, percent: assetPercent, color: stageColor(assetPercent), statusClass: statusClass(assetPercent) },
    { key: 'spd', icon: '\u{1F6E1}', name: t.value.risk.chainSPD, count: `${tb?.threat_count ?? 0} / ${tb?.assumption_count ?? 0} / ${tb?.osp_count ?? 0}`, percent: spdPercent, color: stageColor(spdPercent), statusClass: statusClass(spdPercent) },
    { key: 'objectives', icon: '\u{1F3AF}', name: t.value.risk.chainObjectives, count: sb?.objective_count ?? 0, percent: objPercent, color: stageColor(objPercent), statusClass: statusClass(objPercent) },
    { key: 'sfrs', icon: '\u{1F512}', name: t.value.risk.chainSFRs, count: sb?.sfr_count ?? 0, percent: sfrPercent, color: stageColor(sfrPercent), statusClass: statusClass(sfrPercent) },
    { key: 'tests', icon: '\u{1F9EA}', name: t.value.risk.chainTests, count: testb?.test_count ?? 0, percent: testPercent, color: stageColor(testPercent), statusClass: statusClass(testPercent) },
  ]
})

// ── Blind Spots ──
const confidenceTagType = computed<'success' | 'warning' | 'error' | 'info'>(() => {
  if (!blindSpots.value) return 'info'
  const c = blindSpots.value.overall_confidence
  if (c === 'very_high') return 'success'
  if (c === 'high') return 'success'
  if (c === 'medium') return 'warning'
  return 'error'
})

const confidenceLabel = computed(() => {
  if (!blindSpots.value) return '-'
  const labels: Record<string, string> = {
    very_high: t.value.risk.confVeryHigh,
    high: t.value.risk.confHigh,
    medium: t.value.risk.confMedium,
    low: t.value.risk.confLow,
  }
  return labels[blindSpots.value.overall_confidence] || blindSpots.value.overall_confidence
})

const blindSpotDimensions = computed(() => {
  if (!blindSpots.value) return []
  const d = blindSpots.value.dimensions
  return [
    { key: 'asset', icon: '📦', title: t.value.risk.bsDimAsset, indicators: d.asset_identification.indicators },
    { key: 'threat', icon: '🛡', title: t.value.risk.bsDimThreat, indicators: d.threat_identification.indicators },
    { key: 'sfr', icon: '🔒', title: t.value.risk.bsDimSfr, indicators: d.sfr_adequacy.indicators },
    { key: 'test', icon: '🧪', title: t.value.risk.bsDimTest, indicators: d.test_depth.indicators },
  ]
})

// All blind spot indicators flattened for the unified list
const allBlindSpotIndicators = computed(() => {
  const items: Array<{ icon: string; dimTitle: string; level: string; message: string }> = []
  for (const dim of blindSpotDimensions.value) {
    for (const ind of dim.indicators) {
      items.push({ icon: dim.icon, dimTitle: dim.title, level: ind.level, message: t.value.risk.bsMessages[ind.message] || ind.message })
    }
  }
  // Sort: critical first, then high, medium, low
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }
  items.sort((a, b) => (order[a.level] ?? 4) - (order[b.level] ?? 4))
  return items
})

// Blind spots tooltip dimension descriptions
const bsTooltipDims = computed(() => [
  { key: 'asset', icon: '📦', title: t.value.risk.bsDimAsset, desc: t.value.risk.bsTooltipAsset },
  { key: 'threat', icon: '🛡', title: t.value.risk.bsDimThreat, desc: t.value.risk.bsTooltipThreat },
  { key: 'sfr', icon: '🔒', title: t.value.risk.bsDimSfr, desc: t.value.risk.bsTooltipSfr },
  { key: 'test', icon: '🧪', title: t.value.risk.bsDimTest, desc: t.value.risk.bsTooltipTest },
])

// ── Charts: Risk Distribution Donut ──
const RISK_COLORS: Record<string, string> = { critical: '#8B0000', high: '#d03050', medium: '#f0a020', low: '#18a058' }
const riskDistOption = computed(() => {
  if (!dashboard.value) return {}
  const rd = dashboard.value.risk_distribution
  const data = Object.entries(rd).filter(([, v]) => (v as number) > 0).map(([k, v]) => ({ name: k.toUpperCase(), value: v }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    color: data.map(d => RISK_COLORS[d.name.toLowerCase()] || '#909399'),
    series: [{ type: 'pie', radius: ['45%', '70%'], center: ['50%', '45%'], avoidLabelOverlap: true, itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 }, label: { show: false }, emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } }, data }],
  }
})

// ── Charts: Residual Distribution Donut ──
const RESIDUAL_COLORS: Record<string, string> = { mitigated: '#18a058', transferred: '#2080f0', avoided: '#36ad6a', accepted: '#f0a020', unassessed: '#909399' }
const residualDistOption = computed(() => {
  if (!dashboard.value) return {}
  const rd = dashboard.value.residual_distribution
  const labels: Record<string, string> = { mitigated: t.value.risk.resMitigated, transferred: t.value.risk.resTransferred, avoided: t.value.risk.resAvoided, accepted: t.value.risk.resAccepted, unassessed: t.value.risk.resUnassessed }
  const data = Object.entries(rd).filter(([, v]) => (v as number) > 0).map(([k, v]) => ({ name: labels[k] || k, value: v }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    color: data.map(d => { const key = Object.entries(labels).find(([, v]) => v === d.name)?.[0] || ''; return RESIDUAL_COLORS[key] || '#909399' }),
    series: [{ type: 'pie', radius: ['45%', '70%'], center: ['50%', '45%'], avoidLabelOverlap: true, itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 }, label: { show: false }, emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } }, data }],
  }
})

// ── Charts: Completeness Radar ──
const radarOption = computed(() => {
  const indicators = [
    { name: t.value.risk.chainAssets, max: 100 },
    { name: t.value.risk.chainSPD, max: 100 },
    { name: t.value.risk.chainObjectives, max: 100 },
    { name: t.value.risk.chainSFRs, max: 100 },
    { name: t.value.risk.chainTests, max: 100 },
  ]
  const values = chainStages.value.map(s => s.percent)
  return {
    tooltip: {},
    radar: { indicator: indicators, shape: 'circle', splitNumber: 4, radius: '65%', axisName: { fontSize: 11 } },
    series: [{ type: 'radar', data: [{ value: values, name: t.value.risk.completeness, areaStyle: { color: 'rgba(24, 160, 88, 0.15)' }, lineStyle: { color: '#18a058' }, itemStyle: { color: '#18a058' } }] }],
  }
})

// ── Key Findings (aggregated) ──
const keyFindings = computed(() => {
  const findings: Array<{ severity: string; text: string; count: number }> = []
  const labels = t.value.risk.findingLabels
  for (const report of [threatReport.value, securityReport.value, testReport.value]) {
    if (report?.findings) {
      for (const f of report.findings) {
        if (f.count > 0) findings.push({ severity: f.severity, text: labels[f.key] || f.key, count: f.count })
      }
    }
  }
  const order: Record<string, number> = { high: 0, medium: 1, low: 2 }
  findings.sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3))
  return findings
})

// ── Threat Table ──
function riskTagType(level: string): 'success' | 'warning' | 'error' | 'default' {
  if (level === 'low') return 'success'
  if (level === 'medium') return 'warning'
  if (level === 'high' || level === 'critical') return 'error'
  return 'default'
}

const CHAIN_STATUS_CONFIG: Record<string, { type: string; order: number }> = {
  fully_assured: { type: 'success', order: 6 },
  partially_tested: { type: 'info', order: 5 },
  tests_unconfirmed: { type: 'warning', order: 4 },
  no_test: { type: 'warning', order: 3 },
  no_sfr: { type: 'error', order: 2 },
  no_objective: { type: 'error', order: 1 },
}

const problemColumns = computed<DataTableColumn[]>(() => [
  {
    title: t.value.risk.colType, key: 'type', width: 100,
    render: (row: any) => {
      const typeMap: Record<string, any> = {
        threat: { label: t.value.risk.typeThreat, type: 'warning' },
        assumption: { label: t.value.risk.typeAssumption, type: 'info' },
        osp: { label: t.value.risk.typeOsp, type: 'default' },
      }
      const info = typeMap[row.type] || { label: row.type, type: 'default' }
      return h(NTag, { type: info.type, size: 'small', round: true }, () => info.label)
    },
  },
  { title: t.value.risk.colCode, key: 'code', width: 140, sorter: 'default' },
  {
    title: t.value.risk.colRisk, key: 'risk_level', width: 100,
    sorter: (a: any, b: any) => { const o: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 }; return (o[a.risk_level] ?? 0) - (o[b.risk_level] ?? 0) },
    render: (row: any) => {
      if (row.type !== 'threat') return h('span', { style: 'color: #909399' }, '-')
      return h(NTag, { type: riskTagType(row.risk_level), size: 'small', round: true }, () => row.risk_level?.toUpperCase())
    },
  },
  {
    title: t.value.risk.colStatus, key: 'review_status', width: 100,
    render: (row: any) => { const m: Record<string, string> = { confirmed: 'success', pending: 'warning', false_positive: 'default', draft: 'default' }; return h(NTag, { type: (m[row.review_status] || 'default') as any, size: 'small', round: true }, () => row.review_status) },
  },
  {
    title: t.value.risk.colObjectives, key: 'objectives', width: 80, align: 'center' as const,
    render: (row: any) => h('span', { style: row.objectives > 0 ? '' : 'color: #d03050; font-weight: 700' }, row.objectives),
  },
  {
    title: t.value.risk.colSfrs, key: 'sfrs', width: 70, align: 'center' as const,
    render: (row: any) => h('span', { style: row.sfrs > 0 ? '' : (row.objectives > 0 ? 'color: #d03050; font-weight: 700' : 'color: #909399') }, row.sfrs),
  },
  {
    title: t.value.risk.colTests, key: 'tests', width: 100, align: 'center' as const,
    render: (row: any) => {
      if (row.tests === 0 && row.sfrs === 0) return h('span', { style: 'color: #909399' }, '-')
      if (row.tests === 0) return h('span', { style: 'color: #d03050; font-weight: 700' }, '0')
      return h('span', {}, `${row.confirmed_tests} / ${row.tests}`)
    },
  },
  {
    title: t.value.risk.colChainStatus, key: 'chain_status', width: 140,
    sorter: (a: any, b: any) => (CHAIN_STATUS_CONFIG[a.chain_status]?.order ?? 0) - (CHAIN_STATUS_CONFIG[b.chain_status]?.order ?? 0),
    render: (row: any) => {
      const cfg = CHAIN_STATUS_CONFIG[row.chain_status] || { type: 'default', order: 0 }
      const label = t.value.risk.chainStatusLabels[row.chain_status] || row.chain_status
      return h(NTag, { type: cfg.type as any, size: 'small', round: true }, () => label)
    },
  },
])

function problemRowClass(row: any) {
  if (row.type === 'threat') {
    if (row.risk_level === 'critical') return 'row-critical'
    if (row.risk_level === 'high') return 'row-high'
  }
  return ''
}

// ── Lifecycle ──
onMounted(loadToes)
watch(() => route.query.toeId, value => {
  if (typeof value === 'string' && value !== selectedToeId.value && toeOptions.value.some(item => item.value === value)) {
    selectedToeId.value = value
    toeSelectionStore.setSelectedToeId(value)
    loadAll()
  }
})
</script>

<style scoped>
.risk-dashboard { max-width: 1400px; }
.section { margin-top: 16px; }

/* ── Executive Summary ── */
.summary-row { display: flex; gap: 16px; align-items: stretch; }
.summary-col-gauge { flex: 0 0 260px; display: flex; flex-direction: column; }
.summary-col-chain { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; }
.summary-card { height: 100%; }
.summary-card.score-card { flex: 1; }
.score-card :deep(.n-card__content) { display: flex; align-items: center; justify-content: center; flex: 1; }
.score-gauge { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
.gauge-ring { width: 90px; height: 90px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.gauge-inner { width: 70px; height: 70px; border-radius: 50%; background: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.gauge-value { font-size: 22px; font-weight: 700; line-height: 1; }
.gauge-label { font-size: 11px; color: #909399; }
.metric-block { text-align: center; padding: 8px 0; }
.metric-value { font-size: 28px; font-weight: 700; color: #303133; line-height: 1.2; }
.metric-unit { font-size: 16px; font-weight: 400; color: #909399; }
.metric-label { font-size: 13px; color: #909399; margin-top: 4px; }
.metric-sub { margin-top: 8px; display: flex; gap: 6px; justify-content: center; }
.metric-card-trigger { display: flex; flex-direction: column; flex: 1; }
.metric-tooltip { max-width: 420px; }
.metric-tooltip-title { font-size: 15px; font-weight: 600; color: #303133; }
.metric-tooltip-label { margin-top: 10px; font-size: 12px; font-weight: 600; color: #606266; text-transform: uppercase; letter-spacing: 0.04em; }
.metric-tooltip-text { margin-top: 6px; font-size: 13px; line-height: 1.6; color: #606266; }
.metric-tooltip-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.metric-tooltip-list { margin: 8px 0 0; padding-left: 18px; color: #303133; }
.metric-tooltip-list li { margin-top: 6px; line-height: 1.6; }

/* ── CC Assurance Chain Pipeline ── */
.chain-pipeline-card { min-height: 200px; }
.chain-pipeline { display: flex; align-items: center; justify-content: center; gap: 0; padding: 16px 0; overflow-x: auto; }
.chain-stage { display: flex; align-items: center; }
.stage-node { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 16px; border-radius: 10px; background: #f9fafb; border: 2px solid #e4e7ed; min-width: 110px; transition: border-color 0.3s, box-shadow 0.3s; }
.stage-node.stage-good { border-color: #18a058; box-shadow: 0 0 0 1px rgba(24, 160, 88, 0.1); }
.stage-node.stage-attention { border-color: #f0a020; box-shadow: 0 0 0 1px rgba(240, 160, 32, 0.1); }
.stage-node.stage-weak { border-color: #d03050; box-shadow: 0 0 0 1px rgba(208, 48, 80, 0.1); }
.stage-icon { font-size: 22px; }
.stage-name { font-size: 12px; font-weight: 600; color: #303133; }
.stage-count { font-size: 14px; font-weight: 700; color: #606266; }
.stage-bar-wrap { width: 70px; height: 5px; background: #e8e8e8; border-radius: 3px; overflow: hidden; }
.stage-bar { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
.stage-percent { font-size: 12px; font-weight: 700; }
.chain-arrow { margin: 0 2px; display: flex; align-items: center; }
.chain-legend { display: flex; gap: 16px; justify-content: center; margin-top: 4px; }
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #909399; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

/* ── Blind Spots ── */
.bs-warning-banner {
  display: flex; align-items: flex-start; gap: 8px; padding: 10px 14px; border-radius: 8px;
  background: #fffbe6; border: 1px solid #ffe58f; margin-bottom: 16px;
}
.bs-warning-icon { font-size: 18px; flex-shrink: 0; line-height: 1.5; }
.bs-warning-text { font-size: 13px; color: #614700; line-height: 1.5; }
.bs-risk-list { margin-bottom: 16px; }
.bs-risk-title { font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 8px; }
.bs-risk-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 13px; color: #303133; border-bottom: 1px solid #f5f5f5; }
.bs-risk-item:last-child { border-bottom: none; }
.bs-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-critical { background: #8B0000; }
.dot-high { background: #d03050; }
.dot-medium { background: #f0a020; }
.dot-low { background: #909399; }
.bs-risk-dim { font-size: 15px; flex-shrink: 0; width: 20px; text-align: center; }
.bs-risk-msg { flex: 1; min-width: 0; }
.bs-all-ok { margin-bottom: 16px; padding: 8px 0; }

/* ── Charts ── */
.chart-card { height: 300px; }

/* ── Key Findings ── */
.findings-list { display: flex; flex-direction: column; gap: 8px; }
.finding-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 6px; background: #f9fafb; }
.finding-high { background: #fef0f0; }
.finding-medium { background: #fdf6ec; }
.finding-badge { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #fff; flex-shrink: 0; }
.badge-high { background: #d03050; }
.badge-medium { background: #f0a020; }
.badge-low { background: #909399; }
.finding-text { flex: 1; font-size: 13px; color: #303133; }
.security-problem-table-wrap { min-height: 720px; }

/* ── Threat Table Row Highlight ── */
:deep(.row-critical td) { background: #fef0f0 !important; }
:deep(.row-high td) { background: #fff8f0 !important; }
</style>
