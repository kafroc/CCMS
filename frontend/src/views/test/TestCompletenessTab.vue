<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px; flex-wrap: wrap">
      <n-space>
        <n-tag :type="summaryTagType" size="large">{{ summaryStatusLabel }}</n-tag>
        <n-text depth="3">{{ report?.summary.basis_note }}</n-text>
      </n-space>
      <n-button :loading="loading" @click="loadReport">{{ t.common.refresh }}</n-button>
    </n-space>

    <n-empty v-if="!loading && !report" :description="t.common.noData" />

    <template v-else-if="report">
      <n-grid :cols="3" :x-gap="16" style="margin-bottom: 16px">
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
      </n-grid>

      <n-grid :cols="2" :x-gap="16" style="margin-bottom: 16px">
        <n-gi>
          <n-card :title="t.threat.coverageMetrics" size="small">
            <n-space vertical :size="12">
              <div v-for="metric in report.metrics.filter(m => m.key !== 'confirmed_sfr_test_coverage')" :key="metric.key">
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
                {{ index + 1 }}. {{ action }}
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
                  <n-thing :title="item.label" :description="item.detail" />
                  <n-button v-if="resolveFixTarget(finding.key)" size="small" secondary @click="goToFix()">
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
import { testApi } from '@/api/tests'
import type { TestCompletenessReport, TestCompletenessMappingGapSection } from '@/api/tests'
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
const report = ref<TestCompletenessReport | null>(null)

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
    const res = await testApi.getCompletenessReport(props.toeId)
    report.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function metricLabel(key: string) {
  const map: Record<string, string> = {
    sfr_test_coverage: t.value.threat.metricSfrTestCoverage,
    confirmed_sfr_test_coverage: t.value.test.metricConfirmedSfrTestCoverage,
  }
  return map[key] || key
}

function findingLabel(key: string) {
  const map: Record<string, string> = {
    sfrs_without_tests: t.value.threat.findingSfrsWithoutTests,
    sfrs_without_confirmed_tests: t.value.test.findingSfrsWithoutConfirmedTests,
    tests_without_steps: t.value.test.findingTestsWithoutSteps,
  }
  return map[key] || key
}

function mappingSectionLabel(key: string) {
  const map: Record<string, string> = {
    sfr_to_tests: t.value.test.mappingSfrToTests,
    sfr_to_confirmed_tests: t.value.test.mappingSfrToConfirmedTests,
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
  return objectiveType === 'O' ? t.value.test.coverageGroupAllTests : t.value.test.coverageGroupConfirmedTests
}

function groupGapCount(group: { sections: TestCompletenessMappingGapSection[] }) {
  return group.sections.reduce((sum, section) => sum + section.gaps.length + section.overflow, 0)
}

function groupGapTagType(group: { sections: TestCompletenessMappingGapSection[] }): 'success' | 'warning' | 'error' {
  const gapCount = groupGapCount(group)
  if (gapCount === 0) return 'success'
  if (gapCount <= 3) return 'warning'
  return 'error'
}

function mappingSectionTagType(section: TestCompletenessMappingGapSection): 'success' | 'warning' | 'error' | 'default' {
  if (section.total === 0) return 'default'
  if (section.covered === section.total) return 'success'
  if (section.covered >= Math.ceil(section.total * 0.6)) return 'warning'
  return 'error'
}

function resolveFixTarget(key: string) {
  return ['sfrs_without_tests', 'sfrs_without_confirmed_tests', 'tests_without_steps'].includes(key)
}

function resolveMappingFixTarget(itemId?: string) {
  return Boolean(itemId)
}

function goToFix() {
  router.push({ name: 'Tests', query: { toeId: props.toeId, tab: 'list' } })
}

function goToMappingFix(itemId?: string) {
  if (!itemId) return
  router.push({ name: 'Tests', query: { toeId: props.toeId, tab: 'list', focusSfrId: itemId } })
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