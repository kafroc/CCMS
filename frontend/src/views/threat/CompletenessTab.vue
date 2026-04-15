<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px; flex-wrap: wrap">
      <n-space>
        <n-tag :type="summaryTagType" size="large">{{ summaryStatusLabel }}</n-tag>
        <n-text depth="3">{{ basisNoteTranslate(report?.summary.basis_note || '') }}</n-text>
      </n-space>
      <n-button :loading="loading" @click="loadReport">{{ t.common.refresh }}</n-button>
    </n-space>

    <n-empty v-if="!loading && !report" :description="t.common.noData" />

    <template v-else-if="report">
      <n-grid :cols="4" :x-gap="16" style="margin-bottom: 16px">
        <n-gi>
          <n-card size="small">
            <n-statistic :label="t.threat.completenessScore" :value="report.summary.score">
              <template #suffix>%</template>
            </n-statistic>
            <n-progress :percentage="report.summary.score" :show-indicator="false" style="margin-top: 12px" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card size="small">
            <n-statistic :label="t.threat.totalFindings" :value="report.summary.total_findings" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card size="small">
            <n-statistic :label="t.threat.highPriorityFindings" :value="report.summary.high_findings" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card size="small">
            <n-statistic :label="t.threat.coverageBasis">
              <template #default>
                {{ report.basis.covered_assets_count }} / {{ report.basis.asset_count }} {{ t.toe.assets }}
              </template>
            </n-statistic>
          </n-card>
        </n-gi>
      </n-grid>

      <n-grid :cols="2" :x-gap="16" style="margin-bottom: 16px">
        <n-gi>
          <n-card :title="t.threat.coverageMetrics" size="small">
            <n-space vertical :size="12">
              <div v-for="metric in report.metrics" :key="metric.key">
                <n-space justify="space-between" align="center" style="margin-bottom: 6px">
                  <span>{{ metricLabel(metric.key) }}</span>
                  <n-tag :type="metricTagType(metric.status)" size="small">
                    {{ metric.covered }}/{{ metric.total || '-' }}
                  </n-tag>
                </n-space>
                <n-progress :percentage="metric.percent" :show-indicator="true" processing />
              </div>
            </n-space>
          </n-card>
        </n-gi>

        <n-gi>
          <n-card :title="t.threat.recommendedActions" size="small">
            <n-list bordered>
              <n-list-item v-for="(action, index) in report.next_actions" :key="index">
                {{ index + 1 }}. {{ translateAction(action) }}
              </n-list-item>
            </n-list>
          </n-card>
        </n-gi>
      </n-grid>

      <n-card :title="t.threat.completenessFindings" size="small">
        <n-space vertical :size="12">
          <n-alert v-if="visibleFindings.length === 0" type="success" :show-icon="false">
            {{ t.threat.noCompletenessGaps }}
          </n-alert>

          <n-card
            v-for="finding in visibleFindings"
            :key="finding.key"
            size="small"
            embedded
            :bordered="true"
          >
            <template #header>
              <n-space justify="space-between" align="center" style="width: 100%">
                <n-space align="center">
                  <strong>{{ findingLabel(finding.key) }}</strong>
                  <n-tag :type="findingTagType(finding.severity)" size="small">{{ findingSeverityLabel(finding.severity) }}</n-tag>
                </n-space>
                <n-text depth="3">{{ finding.count }}</n-text>
              </n-space>
            </template>

            <n-list hoverable>
              <n-list-item v-for="(item, index) in finding.items" :key="`${finding.key}-${index}`">
                <n-space justify="space-between" align="start" style="width: 100%">
                  <n-thing :title="item.label" :description="translateFindingItemDetail(finding.key, item)" />
                  <n-space>
                    <n-button v-if="finding.key === 'lightly_covered_assets' && item.id" size="small" :type="item.ignored ? 'warning' : 'default'" @click="toggleWeakCoverageIgnore(item.id)">
                      {{ item.ignored ? t.threat.ignored : t.threat.ignore }}
                    </n-button>
                    <n-button v-if="resolveFixTarget(finding.key)" size="small" secondary @click="goToFix(finding.key)">
                      {{ t.threat.goToFix }}
                    </n-button>
                  </n-space>
                </n-space>
              </n-list-item>
            </n-list>

            <n-text v-if="finding.overflow > 0" depth="3">
              {{ t.threat.moreFindings.replace('{count}', String(finding.overflow)) }}
            </n-text>
          </n-card>
        </n-space>
      </n-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { threatApi } from '@/api/threats'
import type { ThreatCompletenessReport, CompletenessMappingGapSection } from '@/api/threats'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const props = defineProps<{
  toeId: string
  active: boolean
  refreshToken: number
}>()

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const router = useRouter()

const loading = ref(false)
const report = ref<ThreatCompletenessReport | null>(null)

const visibleFindings = computed(() => (report.value?.findings || []).filter(item => item.count > 0))
const mappingGapGroups = computed(() => {
  const sections = report.value?.mapping_gap_sections || []
  return ['O', 'OE'].map(objectiveType => ({
    objectiveType,
    sections: sections.filter(section => section.objective_type === objectiveType),
  }))
})
const summaryTagType = computed(() => metricTagType(report.value?.summary.status || 'weak'))
const summaryStatusLabel = computed(() => summaryStatusText(report.value?.summary.status || 'weak'))

async function loadReport() {
  if (!props.toeId) return
  loading.value = true
  try {
    const res = await threatApi.getCompletenessReport(props.toeId)
    report.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function metricLabel(key: string) {
  const map: Record<string, string> = {
    asset_coverage: t.value.threat.metricAssetCoverage,
    threat_objective_coverage: t.value.threat.metricThreatObjectiveCoverage,
    assumption_objective_coverage: t.value.threat.metricAssumptionCoverage,
    osp_objective_coverage: t.value.threat.metricOspCoverage,
    objective_sfr_coverage: t.value.threat.metricObjectiveSfrCoverage,
    sfr_test_coverage: t.value.threat.metricSfrTestCoverage,
    risk_assessment_coverage: t.value.threat.metricRiskCoverage,
    reference_alignment: t.value.threat.metricReferenceAlignment,
  }
  return map[key] || key
}

function findingLabel(key: string) {
  const map: Record<string, string> = {
    uncovered_assets: t.value.threat.findingUncoveredAssets,
    lightly_covered_assets: t.value.threat.findingLightlyCoveredAssets,
    interface_gaps: t.value.threat.findingInterfaceGaps,
    threats_without_objectives: t.value.threat.findingThreatsWithoutObjectives,
    threats_without_assets: t.value.threat.findingThreatsWithoutAssets,
    assumptions_without_objectives: t.value.threat.findingAssumptionsWithoutObjectives,
    osps_without_objectives: t.value.threat.findingOspsWithoutObjectives,
    objectives_without_sources: t.value.threat.findingObjectivesWithoutSources,
    objectives_without_sfrs: t.value.threat.findingObjectivesWithoutSfrs,
    sfrs_without_tests: t.value.threat.findingSfrsWithoutTests,
    unassessed_threats: t.value.threat.findingUnassessedThreats,
    reference_gaps: t.value.threat.findingReferenceGaps,
  }
  return map[key] || key
}

function mappingSectionLabel(key: string) {
  const map: Record<string, string> = {
    threat_to_o: t.value.threat.mappingThreatToO,
    threat_to_oe: t.value.threat.mappingThreatToOe,
    assumption_to_o: t.value.threat.mappingAssumptionToO,
    assumption_to_oe: t.value.threat.mappingAssumptionToOe,
    osp_to_o: t.value.threat.mappingOspToO,
    osp_to_oe: t.value.threat.mappingOspToOe,
    objective_o_to_sources: t.value.threat.mappingObjectiveOToSources,
    objective_oe_to_sources: t.value.threat.mappingObjectiveOeToSources,
  }
  return map[key] || key
}

function metricTagType(status: string): 'success' | 'warning' | 'error' | 'default' {
  if (status === 'good') return 'success'
  if (status === 'attention') return 'warning'
  if (status === 'not_applicable') return 'default'
  return 'error'
}

function findingTagType(severity: string): 'warning' | 'error' | 'default' {
  if (severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'default'
}

function findingSeverityLabel(severity: string) {
  if (severity === 'high') return t.value.threat.priorityHigh
  if (severity === 'medium') return t.value.threat.priorityMedium
  return t.value.threat.priorityLow
}

function summaryStatusText(status: string) {
  if (status === 'good') return t.value.threat.completenessGood
  if (status === 'attention') return t.value.threat.completenessAttention
  return t.value.threat.completenessWeak
}

function groupTitle(objectiveType: string) {
  return objectiveType === 'O' ? t.value.security.typeO : t.value.security.typeOE
}

function groupGapCount(group: { sections: CompletenessMappingGapSection[] }) {
  return group.sections.reduce((sum, section) => sum + section.gaps.length + section.overflow, 0)
}

function basisNoteTranslate(note: string): string {
  const map: Record<string, string> = {
    basis_note_threats: t.value.threat.basisNoteThrats,
    basis_note_security: t.value.threat.basisNoteSecurity,
  }
  return map[note] || note
}

function translateAction(action: string): string {
  const map: Record<string, string> = {
    action_cover_uncovered_assets: t.value.threat.actionCoverUncoveredAssets,
    action_threat_objectives: t.value.threat.actionThreatObjectives,
    action_assumption_objectives: t.value.threat.actionAssumptionObjectives,
    action_osp_objectives: t.value.threat.actionOspObjectives,
    action_objectives_sources: t.value.threat.actionObjectivesSources,
    action_sfr_objectives: t.value.threat.actionSfrObjectives,
    action_sfr_no_objectives: t.value.threat.actionSfrNoObjectives,
    action_no_gaps: t.value.threat.actionNoGaps,
  }
  return map[action] || action
}

function translateFindingItemDetail(findingKey: string, item: any): string {
  // Handle lightly covered assets detail
  if (findingKey === 'lightly_covered_assets' && item.detail?.includes('Only associated with')) {
    const match = item.detail.match(/Only associated with (\d+) threat\(s\): (.+)/)
    if (match) {
      return t.value.threat.lightlyCoveredDetail
        ?.replace('{count}', match[1])
        .replace('{threats}', match[2]) || item.detail
    }
  }
  
  // Handle interface gaps detail
  if (findingKey === 'interface_gaps' && item.detail?.includes('Interface appears in TOE')) {
    return t.value.threat.interfaceGapDetail || item.detail
  }
  
  // Handle asset type importance detail (from uncovered assets)
  if (findingKey === 'uncovered_assets' && item.detail?.includes('Importance:')) {
    const match = item.detail.match(/(.+) \/ Importance: (\d+)/)
    if (match) {
      return t.value.threat.assetImportanceDetail
        ?.replace('{type}', match[1])
        .replace('{importance}', match[2]) || item.detail
    }
  }
  
  return item.detail || ''
}

function groupGapTagType(group: { sections: CompletenessMappingGapSection[] }): 'success' | 'warning' | 'error' {
  const gapCount = groupGapCount(group)
  if (gapCount === 0) return 'success'
  if (gapCount <= 3) return 'warning'
  return 'error'
}

function mappingSectionTagType(section: CompletenessMappingGapSection): 'success' | 'warning' | 'error' | 'default' {
  if (section.key === 'threat_to_oe' || section.key === 'osp_to_oe') return 'default'
  if (section.total === 0) return 'default'
  if (section.covered === section.total) return 'success'
  if (section.covered >= Math.ceil(section.total * 0.6)) return 'warning'
  return 'error'
}

function resolveFixTarget(key: string) {
  if (['uncovered_assets', 'lightly_covered_assets'].includes(key)) {
    return { name: 'TOEDetail', params: { id: props.toeId }, query: { tab: 'assets' } }
  }
  if (['threats_without_assets', 'interface_gaps', 'threats_without_objectives', 'reference_gaps'].includes(key)) {
    return { name: 'Threats', query: { toeId: props.toeId, tab: 'threats' } }
  }
  if (key === 'assumptions_without_objectives') {
    return { name: 'Threats', query: { toeId: props.toeId, tab: 'assumptions' } }
  }
  if (key === 'osps_without_objectives') {
    return { name: 'Threats', query: { toeId: props.toeId, tab: 'osps' } }
  }
  if (['objectives_without_sources', 'objectives_without_sfrs'].includes(key)) {
    return { name: 'Security', query: { toeId: props.toeId, tab: 'objectives' } }
  }
  if (key === 'sfrs_without_tests') {
    return { name: 'Tests', query: { toeId: props.toeId } }
  }
  if (key === 'unassessed_threats') {
    return { name: 'Risk', query: { toeId: props.toeId } }
  }
  return null
}

function resolveMappingFixTarget(key: string, itemId?: string) {
  if (!itemId) return null
  if (key.startsWith('threat_to_')) {
    return { name: 'Threats', query: { toeId: props.toeId, tab: 'threats', focusThreatId: itemId } }
  }
  if (key.startsWith('assumption_to_')) {
    return { name: 'Threats', query: { toeId: props.toeId, tab: 'assumptions', focusAssumptionId: itemId } }
  }
  if (key.startsWith('osp_to_')) {
    return { name: 'Threats', query: { toeId: props.toeId, tab: 'osps', focusOspId: itemId } }
  }
  if (key.startsWith('objective_')) {
    return { name: 'Security', query: { toeId: props.toeId, tab: 'objectives', focusObjectiveId: itemId } }
  }
  return null
}

async function toggleWeakCoverageIgnore(assetId: string) {
  try {
    await threatApi.toggleWeakCoverageIgnore(props.toeId, assetId)
    // Refresh the report
    await loadReport()
    message.success(t.value.common.success)
  } catch (e: any) {
    message.error(e.message)
  }
}

function goToFix(key: string) {
  const target = resolveFixTarget(key)
  if (target) {
    router.push(target)
  }
}

function goToMappingFix(key: string, itemId?: string) {
  const target = resolveMappingFixTarget(key, itemId)
  if (target) {
    router.push(target)
  }
}

watch(() => props.toeId, () => {
  report.value = null
  if (props.active) loadReport()
}, { immediate: false })

watch(() => props.active, active => {
  if (active && props.toeId) loadReport()
}, { immediate: false })

watch(() => props.refreshToken, () => {
  if (props.active && props.toeId) loadReport()
})

onMounted(() => {
  if (props.active && props.toeId) loadReport()
})
</script>