<template>
  <div>
    <n-page-header :title="t.test.title" subtitle="">
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
      <n-tabs v-model:value="activeTab" type="line" style="margin-top: 16px">
        <n-tab-pane name="list">
          <template #tab>
            {{ t.test.title }}
            <n-badge v-if="tests.length" :value="tests.length" :max="99" style="margin-left: 6px" />
          </template>

          <!-- Toolbar -->
          <n-space justify="space-between" style="margin: 16px 0 12px">
            <n-space>
              <n-select
                v-model:value="filterStatus"
                :options="statusOptions"
                :placeholder="t.common.status"
                clearable
                style="width: 140px"
              />
            </n-space>
            <n-space>
              <template v-if="currentToeCanWrite && selectedIds.length > 0">
                <n-button size="small" :style="btnStyle" :loading="batchConfirming" @click="batchConfirm">
                  {{ t.test.pass }} ({{ selectedIds.length }})
                </n-button>
                <n-button size="small" :style="btnStyle" :loading="batchDeleting" @click="batchDelete">
                  {{ t.common.delete }} ({{ selectedIds.length }})
                </n-button>
              </template>
              <n-button v-if="currentToeCanWrite" size="small" :style="btnStyle" @click="openAdd">
                {{ t.test.addTest }}
              </n-button>
              <n-button v-if="currentToeCanWrite" size="small" :style="btnStyle" :loading="aiLoading" @click="triggerAiGenerate">
                ✦ {{ t.test.aiSuggestTest }}
              </n-button>
            </n-space>
          </n-space>

          <n-data-table
            :columns="columns"
            :data="filteredTests"
            :loading="loading"
            :row-key="testRowKey"
            v-model:checked-row-keys="selectedIds"
            size="small"
            :scroll-x="900"
          />
        </n-tab-pane>

        <n-tab-pane name="completeness">
          <template #tab>
            {{ t.threat.completenessCheck }}
          </template>
          <TestCompletenessTab
            :toe-id="selectedToeId"
            :active="activeTab === 'completeness'"
            :refresh-token="refreshToken"
          />
        </n-tab-pane>
      </n-tabs>
    </template>

    <!-- AI Progress Modal -->
    <n-modal v-model:show="aiProgressVisible" :closable="false" :mask-closable="false" preset="card" style="width: 440px; border-radius: 8px">
      <template #header>
        <span>✦ {{ t.test.aiSuggestTest }}</span>
      </template>
      <div style="padding: 8px 0">
        <div v-if="aiProgressStatus === 'pending' || aiProgressStatus === 'running'">
          <n-space vertical :size="16">
            <n-progress
              type="line"
              :percentage="aiProgressPct"
              :indicator-placement="'inside'"
              processing
            />
            <div style="color: #666; font-size: 13px">{{ aiProgressMsg }}</div>
          </n-space>
        </div>
        <div v-else-if="aiProgressStatus === 'done'">
          <n-result status="success" :title="aiProgressSummary" />
        </div>
        <div v-else-if="aiProgressStatus === 'failed'">
          <n-result status="error" :title="t.test.generationFailed" :description="aiProgressMsg" />
        </div>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button
            v-if="aiProgressStatus === 'done' || aiProgressStatus === 'failed'"
            :style="btnStyle"
            @click="closeAiProgress"
          >{{ t.test.close }}</n-button>
          <n-button v-else disabled :style="btnStyle">{{ t.test.processing }}</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Edit Drawer -->
    <n-drawer v-model:show="drawerVisible" :width="640" placement="right">
      <n-drawer-content :title="editItem ? t.test.editTest : t.test.addTest" closable>
        <n-form :model="editForm" label-placement="top" size="small" :disabled="!currentToeCanWrite">
          <n-form-item :label="t.test.testCaseId">
            <n-input v-model:value="editForm.case_number" :placeholder="t.test.caseIdPlaceholder" />
          </n-form-item>
          <n-form-item :label="t.test.testName">
            <n-input v-model:value="editForm.title" :placeholder="t.test.namePlaceholder" />
          </n-form-item>

          <n-form-item :label="t.test.linkedSfrs">
            <n-select
              v-model:value="editForm.related_sfr_ids"
              :options="allSfrOptions"
              multiple
              clearable
              filterable
              :placeholder="t.test.selectSfrs"
            />
          </n-form-item>

          <n-form-item :label="t.test.testType">
            <n-checkbox-group v-model:value="editForm.test_type">
              <n-space>
                <n-checkbox value="coverage" :label="t.test.typeCoverage" />
                <n-checkbox value="depth" :label="t.test.typeDepth" />
                <n-checkbox value="independent" :label="t.test.typeIndependent" />
              </n-space>
            </n-checkbox-group>
          </n-form-item>

          <n-divider style="margin: 8px 0">{{ t.test.testCaseDetail }}</n-divider>

          <n-form-item :label="t.test.testPurpose">
            <n-input v-model:value="editForm.objective" type="textarea" :rows="2" :placeholder="t.test.purposePlaceholder" />
          </n-form-item>
          <n-form-item :label="t.test.testTarget">
            <n-input v-model:value="editForm.test_target" type="textarea" :rows="2" :placeholder="t.test.targetPlaceholder" />
          </n-form-item>
          <n-form-item :label="t.test.testScenario">
            <n-input v-model:value="editForm.test_scenario" type="textarea" :rows="2" :placeholder="t.test.scenarioPlaceholder" />
          </n-form-item>
          <n-form-item :label="t.test.testPreconditions">
            <n-input v-model:value="editForm.precondition" type="textarea" :rows="2" :placeholder="t.test.preconditionsPlaceholder" />
          </n-form-item>
          <n-form-item :label="t.test.testSteps">
            <n-input v-model:value="editForm.test_steps" type="textarea" :rows="4" :placeholder="t.test.stepsPlaceholder" />
          </n-form-item>
          <n-form-item :label="t.test.expectedResults">
            <n-input v-model:value="editForm.expected_result" type="textarea" :rows="3" :placeholder="t.test.expectedPlaceholder" />
          </n-form-item>
        </n-form>

        <n-divider />
        <n-space justify="end">
          <n-button :style="btnStyle" @click="drawerVisible = false">{{ t.common.cancel }}</n-button>
          <n-button v-if="currentToeCanWrite" :style="btnStyle" :loading="saveLoading" @click="saveItem">{{ t.common.save }}</n-button>
        </n-space>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, watch } from 'vue'
import { useMessage, NButton, NTag, NSpace, useDialog } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { toeApi } from '@/api/toes'
import { testApi } from '@/api/tests'
import { taskApi } from '@/api/tasks'
import { securityApi } from '@/api/security'
import type { TestCase } from '@/api/tests'
import type { DataTableColumns } from 'naive-ui'
import TestCompletenessTab from './TestCompletenessTab.vue'
import { useLocaleStore } from '@/stores/locale'
import { useToeSelectionStore } from '@/stores/toeSelection'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const toeSelectionStore = useToeSelectionStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const dialog = useDialog()
const route = useRoute()
const router = useRouter()

const btnStyle = { backgroundColor: '#fff', color: '#000', border: '1px solid #d9d9d9' }

// TOE selection
const toeList = ref<any[]>([])
const selectedToeId = ref<string | null>(null)
const activeTab = ref('list')
const refreshToken = ref(0)
const toeOptions = computed(() => toeList.value.map(item => ({ label: item.name, value: item.id })))
const currentToe = computed(() => toeList.value.find(item => item.id === selectedToeId.value) ?? null)
const currentToeCanWrite = computed(() => currentToe.value?.access_level !== 'read')

// Data
const tests = ref<TestCase[]>([])
const loading = ref(false)
const filterStatus = ref<string | null>(null)
const allSfrOptions = ref<any[]>([])

const statusOptions = computed(() => [
  { label: t.value.test.pending, value: 'draft' },
  { label: t.value.test.pass, value: 'confirmed' },
  { label: t.value.test.fail, value: 'rejected' },
])

const filteredTests = computed(() => {
  let list = tests.value
  if (filterStatus.value) list = list.filter(tc => tc.review_status === filterStatus.value)
  return list
})

function testRowKey(row: TestCase) {
  return row.id
}

// Selection & batch
const selectedIds = ref<string[]>([])
const batchConfirming = ref(false)
const batchDeleting = ref(false)

async function batchConfirm() {
  if (!selectedIds.value.length) return
  dialog.warning({
    title: t.value.common.confirm,
    content: t.value.test.batchConfirmPrompt.replace('{count}', String(selectedIds.value.length)),
    positiveText: t.value.common.confirm,
    negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      batchConfirming.value = true
      try {
        await testApi.batchConfirm(selectedToeId.value!, selectedIds.value)
        message.success(t.value.common.success)
        selectedIds.value = []
        loadTests()
      } catch (e: any) { message.error(e.message) }
      finally { batchConfirming.value = false }
    },
  })
}

async function batchDelete() {
  if (!selectedIds.value.length) return
  dialog.warning({
    title: t.value.common.confirmDelete,
    content: t.value.test.batchDeletePrompt.replace('{count}', String(selectedIds.value.length)),
    positiveText: t.value.common.delete,
    negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      batchDeleting.value = true
      try {
        await testApi.batchDelete(selectedToeId.value!, selectedIds.value)
        message.success(t.value.common.success)
        selectedIds.value = []
        loadTests()
      } catch (e: any) { message.error(e.message) }
      finally { batchDeleting.value = false }
    },
  })
}

// Columns (resizable)
const columns = computed<DataTableColumns<TestCase>>(() => [
  { type: 'selection', fixed: 'left', width: 40 },
  {
    title: t.value.test.testCaseId,
    key: 'case_number',
    width: 130,
    resizable: true,
    render: row => h('span', {}, row.case_number || row.id.substring(0, 8).toUpperCase()),
  },
  {
    title: t.value.test.testName,
    key: 'title',
    minWidth: 200,
    resizable: true,
    ellipsis: { tooltip: true },
  },
  {
    title: t.value.test.testCaseDetail,
    key: 'detail',
    width: 260,
    resizable: true,
    render: row => {
      const preview = row.objective || row.test_target || row.test_scenario || '-'
      const short = preview.length > 80 ? preview.substring(0, 80) + '...' : preview
      return h('span', { style: 'color: #666; font-size: 12px' }, short)
    },
  },
  {
    title: t.value.test.testType,
    key: 'test_type',
    width: 160,
    resizable: true,
    render: row => {
      let types: string[] = []
      try { types = typeof row.test_type === 'string' ? JSON.parse(row.test_type) : (Array.isArray(row.test_type) ? row.test_type : []) } catch { types = [row.test_type] }
      if (!types.length) return h('span', { style: 'color: #bbb' }, '-')
      return h(NSpace, { size: 4, wrap: true }, () => types.map((t: string) => h(NTag, { size: 'small' }, () => t.charAt(0).toUpperCase() + t.slice(1))))
    },
  },
  {
    title: t.value.test.linkedSfrs,
    key: 'related_sfr_labels',
    width: 200,
    resizable: true,
    render: row => {
      const labels = row.related_sfr_labels ?? []
      if (!labels.length) return h('span', { style: 'color: #bbb' }, '-')
      return h(NSpace, { size: 4, wrap: true }, () =>
        labels.map((l: string) => h(NTag, { size: 'small' }, () => l))
      )
    },
  },
  {
    title: t.value.common.status,
    key: 'review_status',
    width: 100,
    resizable: true,
    render: row => h(NTag, {
      type: row.review_status === 'confirmed' ? 'success' : row.review_status === 'rejected' ? 'error' : 'default',
      size: 'small',
    }, () => statusLabel(row.review_status)),
  },
  {
    title: t.value.toe.operation,
    key: 'actions',
    width: 90,
    render: row => h(NButton, {
      size: 'tiny',
      style: btnStyle,
      onClick: () => openEdit(row),
    }, () => t.value.common.edit),
  },
])

function statusLabel(s: string) {
  return s === 'confirmed' ? t.value.test.pass : s === 'rejected' ? t.value.test.fail : t.value.test.pending
}

// Drawer / Form
const drawerVisible = ref(false)
const editItem = ref<TestCase | null>(null)
const saveLoading = ref(false)
const editForm = ref({
  case_number: '',
  title: '',
  related_sfr_ids: [] as string[],
  test_type: ['independent'] as string[],
  objective: '',
  test_target: '',
  test_scenario: '',
  precondition: '',
  test_steps: '',
  expected_result: '',
})

function openAdd() {
  editItem.value = null
  editForm.value = { case_number: '', title: '', related_sfr_ids: [], test_type: ['independent'], objective: '', test_target: '', test_scenario: '', precondition: '', test_steps: '', expected_result: '' }
  drawerVisible.value = true
}

function openEdit(item: TestCase) {
  editItem.value = item
  let relatedIds: string[] = []
  try {
    const parsed = item.related_sfr_ids ? JSON.parse(item.related_sfr_ids) : []
    relatedIds = Array.isArray(parsed) ? parsed : []
  } catch { relatedIds = [] }
  let testTypes: string[] = ['independent']
  try {
    const parsedTypes = item.test_type ? JSON.parse(item.test_type) : ['independent']
    testTypes = Array.isArray(parsedTypes) ? parsedTypes : [item.test_type]
  } catch { testTypes = [item.test_type] }
  editForm.value = {
    case_number: item.case_number ?? '',
    title: item.title,
    related_sfr_ids: relatedIds,
    test_type: testTypes,
    objective: item.objective ?? '',
    test_target: item.test_target ?? '',
    test_scenario: item.test_scenario ?? '',
    precondition: item.precondition ?? '',
    test_steps: item.test_steps ?? '',
    expected_result: item.expected_result ?? '',
  }
  drawerVisible.value = true
}

async function saveItem() {
  if (!editForm.value.title.trim()) {
    message.warning(t.value.test.titleRequired)
    return
  }
  if (!editForm.value.related_sfr_ids.length) {
    message.warning(t.value.test.linkedSfrRequired)
    return
  }
  saveLoading.value = true
  try {
    const payload = {
      case_number: editForm.value.case_number || null,
      title: editForm.value.title,
      primary_sfr_id: editForm.value.related_sfr_ids[0],
      related_sfr_ids: JSON.stringify(editForm.value.related_sfr_ids),
      test_type: editForm.value.test_type,
      objective: editForm.value.objective,
      test_target: editForm.value.test_target,
      test_scenario: editForm.value.test_scenario,
      precondition: editForm.value.precondition,
      test_steps: editForm.value.test_steps,
      expected_result: editForm.value.expected_result,
    }
    if (editItem.value) {
      const res = await testApi.update(selectedToeId.value!, editItem.value.id, payload)
      const updated = res.data
      const idx = tests.value.findIndex(tc => tc.id === updated.id)
      if (idx !== -1) tests.value[idx] = updated
    } else {
      await testApi.create(selectedToeId.value!, payload)
    }
    message.success(t.value.common.success)
    drawerVisible.value = false
    loadTests()
  } catch (e: any) { message.error(e.message) }
  finally { saveLoading.value = false }
}

// AI Generation with progress polling
const aiLoading = ref(false)
const aiProgressVisible = ref(false)
const aiProgressStatus = ref<'pending' | 'running' | 'done' | 'failed'>('pending')
const aiProgressMsg = ref('Starting...')
const aiProgressSummary = ref('')
const aiProgressStep = ref(0)
const aiProgressTotal = ref(0)
let aiPollTimer: ReturnType<typeof setTimeout> | null = null

const aiProgressPct = computed(() => {
  if (aiProgressTotal.value === 0) return 0
  const pct = Math.round((aiProgressStep.value / aiProgressTotal.value) * 100)
  return Math.min(pct, 99)
})

function parseProgressMsg(msg: string | null) {
  if (!msg) return
  aiProgressMsg.value = msg
  // try parse "3/8: FDP_ACC.1"
  const m = msg.match(/^(\d+)\/(\d+)/)
  if (m) {
    aiProgressStep.value = parseInt(m[1])
    aiProgressTotal.value = parseInt(m[2])
  }
}

async function pollTask(taskId: string) {
  try {
    const res = await taskApi.get(taskId)
    const task = res.data
    aiProgressStatus.value = task.status
    parseProgressMsg(task.progress_message)
    if (task.status === 'done') {
      aiProgressSummary.value = task.result_summary || t.value.test.generationComplete
      aiProgressStep.value = aiProgressTotal.value
      loadTests()
    } else if (task.status === 'failed') {
      aiProgressMsg.value = task.error_message || t.value.test.unknownError
    } else {
      aiPollTimer = setTimeout(() => pollTask(taskId), 2000)
    }
  } catch {
    aiPollTimer = setTimeout(() => pollTask(taskId), 2000)
  }
}

function closeAiProgress() {
  aiProgressVisible.value = false
  if (aiPollTimer) { clearTimeout(aiPollTimer); aiPollTimer = null }
}

async function triggerAiGenerate() {
  aiLoading.value = true
  try {
    const res = await testApi.aiGenerate(selectedToeId.value!, undefined, localeStore.lang)
    const taskId = res.data?.task_id
    if (!taskId) { message.error(t.value.test.startFailed); return }
    aiProgressStatus.value = 'pending'
    aiProgressMsg.value = t.value.threat.initTask
    aiProgressStep.value = 0
    aiProgressTotal.value = 0
    aiProgressSummary.value = ''
    aiProgressVisible.value = true
    aiPollTimer = setTimeout(() => pollTask(taskId), 1000)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    aiLoading.value = false
  }
}

// Data loading
async function loadToes() {
  const res = await toeApi.list()
  toeList.value = res.data
  const routeToeId = typeof route.query.toeId === 'string' ? route.query.toeId : null
  const routeTab = typeof route.query.tab === 'string' ? route.query.tab : null
  const storedToeId = toeSelectionStore.selectedToeId
  if (routeTab && ['list', 'completeness'].includes(routeTab)) {
    activeTab.value = routeTab
  }
  const initialToeId = routeToeId && res.data.some((item: any) => item.id === routeToeId)
    ? routeToeId
    : storedToeId && res.data.some((item: any) => item.id === storedToeId)
      ? storedToeId
      : res.data[0]?.id
  if (initialToeId) {
    selectedToeId.value = initialToeId
    toeSelectionStore.setSelectedToeId(initialToeId)
    onToeChange(initialToeId)
  }
}

function onToeChange(id: string) {
  selectedToeId.value = id
  toeSelectionStore.setSelectedToeId(id)
  router.replace({ name: 'Tests', query: { ...route.query, toeId: id, tab: activeTab.value } })
  selectedIds.value = []
  loadTests()
  loadSFROptions()
  refreshToken.value += 1
}

async function loadTests() {
  if (!selectedToeId.value) return
  loading.value = true
  try {
    const sfrId = typeof route.query.sfrId === 'string' ? route.query.sfrId : undefined
    const res = await testApi.list(selectedToeId.value, sfrId ? { sfr_id: sfrId } : undefined)
    tests.value = res.data
  } catch (e: any) { message.error(e.message) }
  finally { loading.value = false; refreshToken.value += 1 }
}

async function loadSFROptions() {
  if (!selectedToeId.value) return
  try {
    const res = await securityApi.listSFRs(selectedToeId.value)
    allSfrOptions.value = res.data.map((s: any) => ({ label: s.sfr_id, value: s.id }))
  } catch (_) {}
}

onMounted(loadToes)

watch(activeTab, value => {
  if (selectedToeId.value) {
    router.replace({ name: 'Tests', query: { ...route.query, toeId: selectedToeId.value, tab: value } })
  }
})

watch(() => route.query.toeId, value => {
  if (typeof value === 'string' && value !== selectedToeId.value && toeList.value.some(item => item.id === value)) {
    onToeChange(value)
  }
})

watch(() => route.query.tab, value => {
  if (typeof value === 'string' && ['list', 'completeness'].includes(value) && value !== activeTab.value) {
    activeTab.value = value
  }
})
</script>
