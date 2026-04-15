<template>
  <div>
    <n-page-header :title="t.security.title" subtitle="">
      <template #extra>
        <n-select
          v-model:value="selectedToeId"
          :options="toeOptions"
          :placeholder="t.threat.selectToe"
          style="width: 260px"
          @update:value="onToeChange"
        />
      </template>
    </n-page-header>

    <div v-if="!selectedToeId" style="margin-top: 80px; text-align: center">
      <n-empty :description="t.threat.selectToeTip" />
    </div>

    <template v-else>
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane name="objectives">
          <template #tab>
            {{ t.security.securityObjectives }}
            <n-badge v-if="objectives.length" :value="objectives.length" :max="99" style="margin-left: 6px" />
          </template>
          <ObjectivesTab
            ref="objectivesTabRef"
            :toe-id="selectedToeId"
            :objectives="objectives"
            :threats="threats"
            :assumptions="assumptions"
            :osps="osps"
            :sfrs="sfrs"
            :objective-sources-map="objectiveSourcesMap"
            :loading="objectivesLoading"
            :can-write="currentToeCanWrite"
            @refresh="refreshAll"
          >
            <template #actions>
              <n-button v-if="currentToeCanWrite" @click="openAddObjective">+ {{ t.security.addObjective }}</n-button>
              <n-button v-if="currentToeCanWrite" @click="aiSuggestObjectives">
                <template #icon><n-icon><BulbOutline /></n-icon></template>
                {{ t.security.aiSuggest }}
              </n-button>
              <n-button v-if="currentToeCanWrite" :loading="importLoading" @click="handleImport">
                <template #icon><n-icon><DocumentOutline /></n-icon></template>
                {{ t.security.importFromDoc }}
              </n-button>
            </template>
          </ObjectivesTab>
        </n-tab-pane>

        <n-tab-pane name="sfrs">
          <template #tab>
            {{ t.security.sfrs }}
            <n-badge v-if="sfrs.length" :value="sfrs.length" :max="99" style="margin-left: 6px" />
          </template>
          <SFRsTab
            :toe-id="selectedToeId"
            :objectives="objectives"
            :sfrs="sfrs"
            :loading="sfrsLoading"
            :can-write="currentToeCanWrite"
            @refresh="refreshAll"
          />
        </n-tab-pane>

        <n-tab-pane name="completeness">
          <template #tab>
            {{ t.threat.completenessCheck }}
          </template>
          <SecurityCompletenessTab
            :toe-id="selectedToeId"
            :active="activeTab === 'completeness'"
            :refresh-token="refreshToken"
          />
        </n-tab-pane>

        <n-tab-pane name="sfr_library">
          <template #tab>
            {{ t.security.sfrLibrary }}
            <n-badge :value="sfrLibraryCount" :max="999" :show-zero="true" style="margin-left: 6px" />
          </template>
          <SFRLibraryTab @stats="handleSfrLibraryStats" />
        </n-tab-pane>
      </n-tabs>
    </template>

    <!-- Import from ST/PP confirmation + progress modal -->
    <n-modal v-model:show="importModalVisible" :mask-closable="false" preset="card" :title="t.security.importFromDoc" style="width: 520px">
      <!-- Stage 1: show the discovered file list -->
      <template v-if="importStage === 'confirm'">
        <p style="margin-bottom: 12px; color: #333">{{ t.threat.foundStPpFiles }}:</p>
        <n-list bordered size="small" style="margin-bottom: 16px">
          <n-list-item v-for="f in importFiles" :key="f.id">
            <n-thing :title="f.original_filename" :description="f.process_status === 'ready' ? '✓ ' + t.threat.parsed : '⏳ ' + t.threat.parsing" />
          </n-list-item>
        </n-list>
        <p style="color: #999; font-size: 12px">{{ t.threat.importConfirmTip }}</p>
      </template>
      <!-- Stage 2: progress -->
      <template v-else>
        <div style="text-align: center; padding: 16px 0">
          <n-progress
            type="line"
            :percentage="importProgress"
            :indicator-placement="'inside'"
            style="margin-bottom: 16px"
          />
          <p style="color: #666; font-size: 13px">{{ importStatusMsg }}</p>
        </div>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button v-if="importStage === 'confirm'" @click="closeImportModal">{{ t.common.cancel }}</n-button>
          <n-button v-if="importStage === 'confirm'" type="primary" :loading="importRunning" @click="startImportTask">
            {{ t.threat.startImport }}
          </n-button>
          <n-button v-else :disabled="importProgress < 100 && importProgress > 0 && !importFailed" @click="closeImportModal">
            {{ importProgress >= 100 || importFailed ? t.threat.complete : t.threat.runInBackground }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { DocumentOutline, BulbOutline } from '@vicons/ionicons5'
import { useRoute, useRouter } from 'vue-router'
import { toeApi } from '@/api/toes'
import { threatApi } from '@/api/threats'
import { securityApi } from '@/api/security'
import { taskApi } from '@/api/tasks'
import type { SecurityObjective, SFRInstance, ObjectiveSources } from '@/api/security'
import type { Threat, Assumption, OSP } from '@/api/threats'
import ObjectivesTab from './ObjectivesTab.vue'
import SFRsTab from './SFRsTab.vue'
import SFRLibraryTab from './SFRLibraryTab.vue'
import SecurityCompletenessTab from './SecurityCompletenessTab.vue'
import { useLocaleStore } from '@/stores/locale'
import { useToeSelectionStore } from '@/stores/toeSelection'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const toeSelectionStore = useToeSelectionStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const route = useRoute()
const router = useRouter()

const toeList = ref<any[]>([])
const selectedToeId = ref<string | null>(null)
const activeTab = ref('objectives')
const refreshToken = ref(0)
const threats = ref<Threat[]>([])
const assumptions = ref<Assumption[]>([])
const osps = ref<OSP[]>([])
const objectiveSourcesMap = ref<Record<string, ObjectiveSources>>({})
const sfrLibraryCount = ref(0)

const toeOptions = computed(() =>
  toeList.value.map(t => ({ label: t.name, value: t.id }))
)

const currentToe = computed(() => toeList.value.find(item => item.id === selectedToeId.value) ?? null)
const currentToeCanWrite = computed(() => currentToe.value?.access_level !== 'read')

function buildSecurityQuery(toeId: string, tab: string) {
  return {
    ...route.query,
    toeId,
    tab,
  }
}

async function loadToes() {
  try {
    const res = await toeApi.list()
    toeList.value = res.data
    const routeToeId = typeof route.query.toeId === 'string' ? route.query.toeId : null
    const storedToeId = toeSelectionStore.selectedToeId
    const initialToeId = routeToeId && res.data.some((item: any) => item.id === routeToeId)
      ? routeToeId
      : storedToeId && res.data.some((item: any) => item.id === storedToeId)
        ? storedToeId
        : res.data[0]?.id
    const routeTab = typeof route.query.tab === 'string' ? route.query.tab : null
    if (routeTab && ['objectives', 'sfrs', 'completeness', 'sfr_library'].includes(routeTab)) {
      activeTab.value = routeTab
    }
    if (initialToeId && !selectedToeId.value) {
      selectedToeId.value = initialToeId
      toeSelectionStore.setSelectedToeId(initialToeId)
      onToeChange(initialToeId)
    }
  } catch (e: any) {
    message.error(e.message)
  }
}

function onToeChange(id: string) {
  selectedToeId.value = id
  toeSelectionStore.setSelectedToeId(id)
  router.replace({ name: 'Security', query: buildSecurityQuery(id, activeTab.value) })
  refreshAll()
  loadSFRs()
}

function handleSfrLibraryStats(total: number) {
  sfrLibraryCount.value = total
}

async function loadSfrLibraryCount() {
  try {
    const res = await securityApi.listSFRLibrary({ page: 1, page_size: 1 })
    sfrLibraryCount.value = res.data.total
  } catch (e: any) {
    message.error(e.message)
  }
}

function refreshAll() {
  loadObjectives()
  loadSources()
  loadSFRs()
  refreshToken.value += 1
}

const objectives = ref<SecurityObjective[]>([])
const objectivesLoading = ref(false)
async function loadObjectives() {
  if (!selectedToeId.value) return
  objectivesLoading.value = true
  try {
    const res = await securityApi.listObjectives(selectedToeId.value)
    objectives.value = res.data
    const mappingEntries = await Promise.all(
      res.data.map(async objective => {
        const sourceRes = await securityApi.listObjectiveSources(selectedToeId.value!, objective.id)
        return [objective.id, sourceRes.data] as const
      })
    )
    objectiveSourcesMap.value = Object.fromEntries(mappingEntries)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    objectivesLoading.value = false
  }
}

async function loadSources() {
  if (!selectedToeId.value) return
  try {
    const [threatRes, assumptionRes, ospRes] = await Promise.all([
      threatApi.listThreats(selectedToeId.value),
      threatApi.listAssumptions(selectedToeId.value),
      threatApi.listOsps(selectedToeId.value),
    ])
    threats.value = threatRes.data
    assumptions.value = assumptionRes.data
    osps.value = ospRes.data
  } catch (e: any) {
    message.error(e.message)
  }
}

const sfrs = ref<SFRInstance[]>([])
const sfrsLoading = ref(false)
async function loadSFRs() {
  if (!selectedToeId.value) return
  sfrsLoading.value = true
  try {
    const res = await securityApi.listSFRs(selectedToeId.value)
    sfrs.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    sfrsLoading.value = false
  }
}

onMounted(() => {
  loadToes()
  loadSfrLibraryCount()
})

watch(activeTab, value => {
  if (selectedToeId.value) {
    router.replace({ name: 'Security', query: buildSecurityQuery(selectedToeId.value, value) })
  }
})

watch(() => route.query.toeId, value => {
  if (typeof value === 'string' && value !== selectedToeId.value && toeList.value.some(item => item.id === value)) {
    onToeChange(value)
  }
})

watch(() => route.query.tab, value => {
  if (typeof value === 'string' && ['objectives', 'sfrs', 'completeness', 'sfr_library'].includes(value) && value !== activeTab.value) {
    activeTab.value = value
  }
})

// ── Objective Management ──
const objectivesTabRef = ref<any>(null)
const importLoading = ref(false)
const importModalVisible = ref(false)
const importTaskId = ref<string | null>(null)
const importProgress = ref(0)
const importTargetProgress = ref(0)
const importStatusMsg = ref('')
const importFailed = ref(false)
const importStage = ref<'confirm' | 'progress'>('confirm')
const importFiles = ref<any[]>([])
const importRunning = ref(false)
let importTimer: ReturnType<typeof setInterval> | null = null
let importProgressTimer: ReturnType<typeof setInterval> | null = null

function openAddObjective() {
  // Call ObjectivesTab's openAdd method via ref
  objectivesTabRef.value?.openAdd?.()
}

function aiSuggestObjectives() {
  if (!selectedToeId.value) return
  if (!currentToeCanWrite.value) return
  if (!objectivesTabRef.value?.startAiGenerate) {
    message.error(t.value.common.error)
    return
  }
  objectivesTabRef.value.startAiGenerate('incremental')
}

async function handleImport() {
  importLoading.value = true
  try {
    if (!selectedToeId.value) return
    const res = await toeApi.listFiles(selectedToeId.value, 'st_pp')
    const allStpp = res.data ?? []
    if (allStpp.length === 0) {
      message.warning(t.value.threat.noStPpDocs)
      return
    }
    const readyFiles = allStpp.filter((f: any) => f.process_status === 'ready')
    if (readyFiles.length === 0) {
      message.warning(t.value.threat.stPpNotReady)
      return
    }
    importFiles.value = readyFiles
    importStage.value = 'confirm'
    importModalVisible.value = true
    importProgress.value = 0
    importStatusMsg.value = ''
    importFailed.value = false
  } catch (e: any) {
    message.error(e.message)
  } finally {
    importLoading.value = false
  }
}

async function startImportTask() {
  importRunning.value = true
  try {
    if (!selectedToeId.value) return
    importStage.value = 'progress'
    importProgress.value = 0
    importTargetProgress.value = 0
    importStatusMsg.value = t.value.threat.initTask
    const taskRes = await securityApi.importObjectivesFromDocs(selectedToeId.value)
    importTaskId.value = taskRes.data.task_id
    startImportPolling()
  } catch (e: any) {
    importStatusMsg.value = `${t.value.threat.submitFailed}: ${e.message}`
    importFailed.value = true
  } finally {
    importRunning.value = false
  }
}

function applyTemplate(template: string, current: string, total: string) {
  return template
    .replace('{current}', current)
    .replace('{total}', total)
}

function parseBatchProgress(msg: string, prefix: string) {
  if (!msg.startsWith(prefix)) return null
  const parts = msg.split('|')
  return {
    current: Number(parts[1] ?? '0'),
    total: Number(parts[2] ?? '0'),
  }
}

function translateProgress(msg: string | null): string {
  if (!msg) return t.value.threat.processing
  const progressMap: Record<string, string> = {
    'objective_import.stage_1': t.value.security.importStage1,
    'objective_import.stage_1.scan': t.value.security.importStage1,
    'objective_import.stage_2': t.value.security.importStage2,
    'objective_import.stage_2.prepare': t.value.security.importStage2Prepare,
    'objective_import.stage_2.ai': t.value.security.importStage2Ai,
    'objective_import.stage_2.persist': t.value.security.importStage2Persist,
    'objective_import.stage_3.prepare': t.value.security.importStage3Prepare,
  }
  if (progressMap[msg]) return progressMap[msg]
  const extractProgress = parseBatchProgress(msg, 'objective_import.stage_1.extract|')
  if (extractProgress) {
    return applyTemplate(
      t.value.security.importStage1Extract,
      String(extractProgress.current),
      String(extractProgress.total),
    )
  }
  if (msg === 'Stage 1/3: Reading ST/PP documents...') {
    return t.value.security.importStage1
  }
  if (msg === 'Stage 2/3: Security objectives imported, preparing SFRs...') {
    return t.value.security.importStage2
  }
  const batchStart = parseBatchProgress(msg, 'objective_import.stage_3.batch_start|')
  if (batchStart) {
    return applyTemplate(t.value.security.importStage3Batch, String(batchStart.current), String(batchStart.total))
  }
  const batchAi = parseBatchProgress(msg, 'objective_import.stage_3.batch_ai|')
  if (batchAi) {
    return applyTemplate(t.value.security.importStage3BatchAi, String(batchAi.current), String(batchAi.total))
  }
  const batchSave = parseBatchProgress(msg, 'objective_import.stage_3.batch_save|')
  if (batchSave) {
    return applyTemplate(t.value.security.importStage3BatchSave, String(batchSave.current), String(batchSave.total))
  }
  const legacyBatchMatch = msg.match(/^Stage 3\/3: Mapping SFR batch\s+(\d+)\/(\d+)$/)
  if (legacyBatchMatch) {
    return t.value.security.importStage3Batch
      .replace('{current}', legacyBatchMatch[1] ?? '0')
      .replace('{total}', legacyBatchMatch[2] ?? '0')
  }
  if (msg.startsWith('objective_import.done|')) {
    const parts = msg.split('|')
    return t.value.security.importDone
      .replace('{totalObjectives}', parts[1] ?? '0')
      .replace('{totalSfrs}', parts[2] ?? '0')
      .replace('{newObjectives}', parts[3] ?? '0')
      .replace('{newSfrs}', parts[4] ?? '0')
  }
  return msg
}

function resolveBatchPhaseProgress(current: number, total: number, phaseOffset: number): number {
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
    return 64
  }
  const stepIndex = Math.max(0, (current - 1) * 3 + phaseOffset)
  const stepTotal = Math.max(1, total * 3)
  return Math.min(99, Math.round(64 + (stepIndex / stepTotal) * 32))
}

function resolveImportProgress(msg: string | null, status: string): number {
  if (status === 'done') return 100
  if (!msg) return 0
  if (msg === 'objective_import.stage_1' || msg === 'Stage 1/3: Reading ST/PP documents...') return 20
  if (msg === 'objective_import.stage_1.scan') return 8
  const extractProgress = parseBatchProgress(msg, 'objective_import.stage_1.extract|')
  if (extractProgress) {
    if (!Number.isFinite(extractProgress.current) || !Number.isFinite(extractProgress.total) || extractProgress.total <= 0) {
      return 12
    }
    return Math.min(28, Math.round(8 + (extractProgress.current / extractProgress.total) * 20))
  }
  if (msg === 'objective_import.stage_2' || msg === 'Stage 2/3: Security objectives imported, preparing SFRs...') return 58
  if (msg === 'objective_import.stage_2.prepare') return 34
  if (msg === 'objective_import.stage_2.ai') return 46
  if (msg === 'objective_import.stage_2.persist') return 58
  if (msg === 'objective_import.stage_3.prepare') return 64
  const batchStart = parseBatchProgress(msg, 'objective_import.stage_3.batch_start|')
  if (batchStart) {
    return resolveBatchPhaseProgress(batchStart.current, batchStart.total, 0)
  }
  const batchAi = parseBatchProgress(msg, 'objective_import.stage_3.batch_ai|')
  if (batchAi) {
    return resolveBatchPhaseProgress(batchAi.current, batchAi.total, 1)
  }
  const batchSave = parseBatchProgress(msg, 'objective_import.stage_3.batch_save|')
  if (batchSave) {
    return resolveBatchPhaseProgress(batchSave.current, batchSave.total, 2)
  }
  const legacyBatchMatch = msg.match(/^Stage 3\/3: Mapping SFR batch\s+(\d+)\/(\d+)$/)
  if (legacyBatchMatch) {
    const current = Number(legacyBatchMatch[1] ?? '0')
    const total = Number(legacyBatchMatch[2] ?? '0')
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
      return 64
    }
    return Math.min(99, Math.round(64 + (current / total) * 32))
  }
  return importTargetProgress.value
}

function startImportProgressAnimation() {
  if (importProgressTimer) return
  importProgressTimer = setInterval(() => {
    if (importProgress.value >= importTargetProgress.value) {
      stopImportProgressAnimation()
      return
    }
    importProgress.value = Math.min(importTargetProgress.value, importProgress.value + 1)
  }, 180)
}

function stopImportProgressAnimation() {
  if (importProgressTimer) {
    clearInterval(importProgressTimer)
    importProgressTimer = null
  }
}

function updateImportProgress(target: number) {
  importTargetProgress.value = Math.max(importTargetProgress.value, Math.min(target, 99))
  if (importProgress.value < importTargetProgress.value) {
    startImportProgressAnimation()
  }
}

function startImportPolling() {
  importTimer = setInterval(async () => {
    if (!importTaskId.value) return
    try {
      const res = await taskApi.get(importTaskId.value)
      const task = res.data
      if (task.status === 'done') {
        stopImportProgressAnimation()
        importTargetProgress.value = 100
        importProgress.value = 100
        importStatusMsg.value = translateProgress(task.result_summary)
        stopImportPolling()
        refreshAll()
      } else if (task.status === 'failed') {
        stopImportProgressAnimation()
        importProgress.value = 0
        importTargetProgress.value = 0
        importStatusMsg.value = `${t.value.threat.scanFailed}: ${task.error_message ?? ''}`
        importFailed.value = true
        stopImportPolling()
      } else {
        updateImportProgress(resolveImportProgress(task.progress_message, task.status))
        importStatusMsg.value = translateProgress(task.progress_message)
      }
    } catch (_) { /* ignore */ }
  }, 2000)
}

function stopImportPolling() {
  if (importTimer) { clearInterval(importTimer); importTimer = null }
  stopImportProgressAnimation()
}

function closeImportModal() {
  importModalVisible.value = false
  stopImportPolling()
}
</script>