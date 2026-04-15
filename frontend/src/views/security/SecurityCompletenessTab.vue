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
      <n-grid :cols="3" :x-gap="16" style="margin-bottom: 16px">
        <n-gi>
          <n-card size="small" content-style="min-height: 122px; display: flex; flex-direction: column; justify-content: space-between;">
            <n-statistic :label="t.threat.completenessScore" :value="report.summary.score">
              <template #suffix>%</template>
            </n-statistic>
            <n-progress :percentage="report.summary.score" :show-indicator="false" style="margin-top: 12px" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card size="small" content-style="min-height: 122px; display: flex; flex-direction: column; justify-content: flex-start;">
            <n-statistic :label="t.threat.totalFindings" :value="report.summary.total_findings" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card size="small" content-style="min-height: 122px; display: flex; flex-direction: column; justify-content: flex-start;">
            <n-statistic :label="t.threat.highPriorityFindings" :value="report.summary.high_findings" />
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

          <n-card v-for="finding in visibleFindings" :key="finding.key" size="small" embedded :bordered="true">
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
                  <n-thing :title="item.label" :description="findingDetail(finding.key, item.detail)" />
                  <n-button v-if="resolveFixTarget(finding.key)" size="small" secondary @click="goToFix(finding.key)">
                    {{ t.threat.goToFix }}
                  </n-button>
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
import { securityApi } from '@/api/security'
import type { SecurityCompletenessReport } from '@/api/security'
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
const report = ref<SecurityCompletenessReport | null>(null)

const visibleFindings = computed(() => (report.value?.findings || []).filter(item => item.count > 0))
const summaryTagType = computed(() => metricTagType(report.value?.summary.status || 'weak'))
const summaryStatusLabel = computed(() => summaryStatusText(report.value?.summary.status || 'weak'))

async function loadReport() {
  if (!props.toeId) return
  loading.value = true
  try {
    const res = await securityApi.getCompletenessReport(props.toeId)
    report.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function metricLabel(key: string) {
  const fallbackMap: Record<string, string> = {
    security_problem_objective_coverage: t.value.security.metricSecurityProblemObjectiveCoverage,
    objective_sfr_coverage: t.value.security.metricObjectiveSfrCoverage,
    sfr_dependency_coverage: t.value.security.metricSfrDependencyCoverage,
  }

  const map: Record<string, string | undefined> = {
    security_problem_objective_coverage: t.value.security.metricSecurityProblemObjectiveCoverage,
    objective_sfr_coverage: t.value.security.metricObjectiveSfrCoverage,
    sfr_dependency_coverage: t.value.security.metricSfrDependencyCoverage,
  }
  return map[key] || fallbackMap[key] || key
}

function findingLabel(key: string) {
  const fallbackMap: Record<string, string> = {
    objectives_without_sfrs: t.value.security.findingObjectivesWithoutSfrs,
    redundant_sfrs: t.value.security.findingRedundantSfrs,
    sfrs_missing_dependencies: t.value.security.findingSfrsMissingDependencies,
  }

  const map: Record<string, string | undefined> = {
    objectives_without_sfrs: t.value.security.findingObjectivesWithoutSfrs,
    redundant_sfrs: t.value.security.findingRedundantSfrs,
    sfrs_missing_dependencies: t.value.security.findingSfrsMissingDependencies,
  }
  return map[key] || fallbackMap[key] || key
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

function basisNoteTranslate(note: string): string {
  const map: Record<string, string> = {
    basis_note_security: t.value.threat.basisNoteSecurity,
  }
  return map[note] || note
}

function findingDetail(key: string, detail: string) {
  if (key !== 'sfrs_missing_dependencies') return detail

  const normalizedDetail = detail
    .replace(/^missing dependencies?\s*[:：]\s*/i, '')

  return `${t.value.security.missingDependenciesPrefix}${normalizedDetail}`
}

function translateAction(action: string): string {
  const map: Record<string, string> = {
    action_sfr_objectives: t.value.threat.actionSfrObjectives,
    action_sfr_dependencies: t.value.security.actionSfrDependencies,
    action_redundant_sfrs: t.value.threat.actionRedundantSfrs,
    action_no_gaps: t.value.threat.actionNoGaps,
  }
  return map[action] || action
}

function resolveFixTarget(key: string) {
  if (key === 'objectives_without_sfrs') {
    return { name: 'Security', query: { toeId: props.toeId, tab: 'objectives' } }
  }
  if (key === 'redundant_sfrs') {
    return { name: 'Security', query: { toeId: props.toeId, tab: 'sfrs' } }
  }
  if (key === 'sfrs_missing_dependencies') {
    return { name: 'Security', query: { toeId: props.toeId, tab: 'sfrs' } }
  }
  return null
}

function goToFix(key: string) {
  const target = resolveFixTarget(key)
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