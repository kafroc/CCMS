<template>
<div>
<!-- Action bar -->
<n-space justify="space-between" style="margin-bottom: 12px; flex-wrap: wrap">
<n-space>
<n-select
v-model:value="filterStatus"
:options="statusOptions"
:placeholder="t.threat.filterStatus"
clearable
style="width: 140px"
/>
<n-select
v-model:value="filterRisk"
:options="riskOptions"
:placeholder="t.threat.filterRisk"
clearable
style="width: 130px"
/>
</n-space>
<n-space>
<!-- Batch actions (shown when items are selected) -->
<template v-if="canWrite && checkedRowKeys.length > 0">
<n-button size="small" :loading="batchConfirming" @click="batchConfirm">
{{ t.threat.confirmThreat }} ({{ checkedRowKeys.length }})
</n-button>
<n-button size="small" :loading="batchDeleting" @click="batchDelete">
{{ t.common.delete }} ({{ checkedRowKeys.length }})
</n-button>
</template>
<!-- Add threat -->
<n-button v-if="canWrite" @click="openAddDrawer">
+ {{ t.threat.addThreat }}
</n-button>
<!-- AI scan -->
<n-button v-if="canWrite" :loading="scanModalVisible && scanProgress < 100" @click="handleAiScan">
<template #icon><n-icon><ScanOutline /></n-icon></template>
{{ t.threat.aiScan }}
</n-button>
<!-- Import from ST/PP -->
<n-button v-if="canWrite" :loading="importLoading" @click="handleImport">
<template #icon><n-icon><DocumentOutline /></n-icon></template>
{{ t.threat.importFromDoc }}
</n-button>
</n-space>
</n-space>

<!-- Threat list -->
<n-data-table
:columns="columns"
:data="filteredThreats"
:loading="loading"
:row-key="(row: Threat) => row.id"
v-model:checked-row-keys="checkedRowKeys"
size="medium"
striped
:scroll-x="900"
/>

<!-- Add threat drawer -->
<n-drawer v-model:show="addDrawerVisible" :width="480" placement="right">
<n-drawer-content :title="t.threat.addThreat" closable>
<n-form :model="addForm" label-placement="top" size="small" :disabled="!canWrite">
<n-form-item :label="t.threat.threatCode">
<n-input v-model:value="addForm.code" placeholder="T.UNAUTH_ACCESS" />
</n-form-item>
<n-form-item :label="t.threat.threatDefinition">
<n-input v-model:value="addForm.definition" type="textarea" :rows="6"
  :placeholder="t.threat.threatDefinitionPlaceholder" />
</n-form-item>
<n-form-item :label="t.threat.linkedAssets">
<n-select
v-model:value="addForm.asset_ids"
:options="assetOptions"
multiple
clearable
filterable
:placeholder="t.threat.selectAssets"
/>
</n-form-item>
<n-form-item :label="t.threat.linkedObjectives">
<n-select
v-model:value="addForm.objective_ids"
:options="objectiveOptions"
multiple
clearable
filterable
:placeholder="t.threat.selectObjectives"
 />
</n-form-item>
</n-form>
<n-divider />
<n-space justify="end">
<n-button @click="addDrawerVisible = false">{{ t.common.cancel }}</n-button>
<n-button v-if="canWrite" type="primary" :loading="addLoading" @click="submitAddThreat">{{ t.common.save }}</n-button>
</n-space>
</n-drawer-content>
</n-drawer>

<!-- Detail drawer on the right -->
<n-drawer v-model:show="drawerVisible" :width="520" placement="right">
<n-drawer-content :title="drawerThreat?.code ?? t.threat.threatDetail" closable>
<template v-if="drawerThreat">
<n-form
ref="formRef"
:model="editForm"
label-placement="top"
size="small"
:disabled="!canWrite"
>
<n-grid :cols="2" :x-gap="12">
<n-form-item-gi :label="t.threat.threatCode">
<n-input v-model:value="editForm.code" />
</n-form-item-gi>
<n-form-item-gi :label="t.threat.reviewStatus">
<n-tag :type="statusTagType(drawerThreat.review_status)" size="small">
{{ statusLabel(drawerThreat.review_status) }}
</n-tag>
</n-form-item-gi>
</n-grid>
<n-form-item :label="t.threat.threatDefinition">
<n-input v-model:value="editForm.definition" type="textarea" :rows="6" />
</n-form-item>
<n-form-item :label="t.threat.linkedAssets">
<n-select
v-model:value="editForm.asset_ids"
:options="assetOptions"
multiple
clearable
filterable
:placeholder="t.threat.selectAssets"
/>
</n-form-item>
<n-form-item :label="t.threat.linkedObjectives">
<n-select
v-model:value="editForm.objective_ids"
:options="objectiveOptions"
multiple
clearable
filterable
:placeholder="t.threat.selectObjectives"
 />
</n-form-item>

<n-form-item v-if="threatObjectiveMap[drawerThreat.id]?.length" :label="t.threat.relatedObjectives">
<n-space size="small" wrap>
<n-button
v-for="objective in threatObjectiveMap[drawerThreat.id]"
:key="objective.id"
size="tiny"
tertiary
@click="goToObjective(objective.id)"
>
{{ objective.code }}
</n-button>
</n-space>
</n-form-item>

<n-form-item :label="t.threat.aiRationale">
<n-input
v-model:value="aiRationaleDisplay"
type="textarea"
:rows="3"
placeholder="—"
readonly
/>
</n-form-item>
<n-form-item :label="t.threat.aiSourceRef">
<n-input v-model:value="editForm.ai_source_ref" placeholder="—" />
</n-form-item>
</n-form>

<n-divider />

<!-- Review actions -->
<n-space justify="space-between">
<n-space v-if="canWrite">
<n-button
type="success"
size="small"
:disabled="drawerThreat.review_status === 'confirmed'"
@click="confirmSingle(drawerThreat)"
>{{ t.threat.confirmThreat }}</n-button>
</n-space>
<n-space>
<n-button size="small" @click="drawerVisible = false">{{ t.common.cancel }}</n-button>
<n-button v-if="canWrite" type="primary" size="small" :loading="saveLoading" @click="saveThreat">{{ t.common.save }}</n-button>
</n-space>
</n-space>
</template>
</n-drawer-content>
</n-drawer>

<!-- AI scan progress modal -->
<n-modal v-model:show="scanModalVisible" :mask-closable="false" preset="card" :title="t.threat.aiScan" style="width: 460px">
<div style="text-align: center; padding: 16px 0">
<n-progress
type="line"
:percentage="scanProgress"
:indicator-placement="'inside'"
style="margin-bottom: 16px"
/>
<p style="color: #666; font-size: 13px">{{ scanStatusMsg }}</p>
<p v-if="scanTaskId" style="color: #aaa; font-size: 11px; margin-top: 8px">Task ID: {{ scanTaskId }}</p>
</div>
<template #footer>
<n-button :disabled="scanProgress < 100 && scanProgress > 0 && !scanFailed" @click="closeScanModal">
{{ scanProgress >= 100 || scanFailed ? t.threat.complete : t.threat.runInBackground }}
</n-button>
</template>
</n-modal>
<!-- Import from ST/PP confirmation + progress modal -->
<n-modal v-model:show="importModalVisible" :mask-closable="false" preset="card" :title="t.threat.importFromDoc" style="width: 520px">
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
<n-button v-if="importStage === 'confirm'" @click="importModalVisible = false">{{ t.common.cancel }}</n-button>
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
import { ref, computed, h, watch, onMounted, type ComputedRef, type Ref } from 'vue'
import { useMessage, NButton, NTag, NSpace, NTooltip, NIcon } from 'naive-ui'
import { ScanOutline, DocumentOutline, AlertCircleOutline } from '@vicons/ionicons5'
import { useRoute, useRouter } from 'vue-router'
import { threatApi } from '@/api/threats'
import { securityApi } from '@/api/security'
import { taskApi } from '@/api/tasks'
import { toeApi } from '@/api/toes'
import type { Threat } from '@/api/threats'
import type { SecurityObjective, ObjectiveSources } from '@/api/security'
import type { TOEAsset } from '@/api/toes'
import type { DataTableColumns } from 'naive-ui'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))

const props = defineProps<{
toeId: string
threats: Threat[]
objectives: SecurityObjective[]
objectiveSourcesMap: Record<string, ObjectiveSources>
loading: boolean
canWrite: boolean
}>()
const emit = defineEmits<{ (e: 'refresh'): void }>()
const message = useMessage()
const route = useRoute()
const router = useRouter()
const canWrite = computed(() => props.canWrite)

// ── Filter ──
const filterStatus = ref<string | null>(null)
const filterRisk = ref<string | null>(null)

const statusOptions = computed(() => [
{ label: t.value.threat.statusPending, value: 'pending' },
{ label: t.value.threat.statusConfirmed, value: 'confirmed' },
{ label: t.value.threat.statusFalsePositive, value: 'false_positive' },
])
const riskOptions = [
{ label: t.value.threat.riskLow, value: 'low' },
{ label: t.value.threat.riskMedium, value: 'medium' },
{ label: t.value.threat.riskHigh, value: 'high' },
{ label: t.value.threat.riskCritical, value: 'critical' },
]
const allRiskOptions = [...riskOptions]
const levelOptions = computed(() => [
{ label: t.value.threat.riskLow, value: 'low' },
{ label: t.value.threat.riskMedium, value: 'medium' },
{ label: t.value.threat.riskHigh, value: 'high' },
])

const filteredThreats = computed(() => {
let list = props.threats
if (filterStatus.value) list = list.filter(t => t.review_status === filterStatus.value)
if (filterRisk.value) list = list.filter(t => t.risk_level === filterRisk.value)
return list
})

// ── Batch select ──
const checkedRowKeys = ref<string[]>([])
const batchConfirming = ref(false)
const batchDeleting = ref(false)
const assets = ref<TOEAsset[]>([])
const assetOptions = computed(() => assets.value.map(item => ({
label: item.name,
value: item.id,
})))
const objectiveOptions = computed(() => props.objectives.map(item => ({
label: `${item.code} (${item.obj_type})`,
value: item.id,
})))

const threatObjectiveMap = computed(() => {
const map: Record<string, SecurityObjective[]> = {}
for (const objective of props.objectives) {
  const threatIds = props.objectiveSourcesMap[objective.id]?.threat_ids ?? []
  for (const threatId of threatIds) {
    if (!map[threatId]) map[threatId] = []
    map[threatId].push(objective)
  }
}
return map
})

// ── Table columns ──
const RISK_MATRIX: Record<string, Record<string, string>> = {
low: { low: 'low', medium: 'low', high: 'medium' },
medium: { low: 'medium', medium: 'medium', high: 'high' },
high: { low: 'medium', medium: 'high', high: 'critical' },
}

function calcRisk(l: string, i: string) {
return RISK_MATRIX[l]?.[i] ?? 'low'
}

function statusTagType(s: string) {
return s === 'confirmed' ? 'success' : s === 'false_positive' ? 'error' : 'default'
}
function statusLabel(s: string) {
return s === 'confirmed' ? t.value.threat.statusConfirmed : s === 'false_positive' ? t.value.threat.statusFalsePositive : t.value.threat.statusPending
}
function riskTagType(r: string) {
return r === 'critical' ? 'error' : r === 'high' ? 'warning' : r === 'medium' ? 'info' : 'default'
}

type ThreatCols = DataTableColumns<Threat>
const columns: ComputedRef<ThreatCols> = computed(() => [
...(canWrite.value ? [{ type: 'selection' as const, fixed: 'left' as const, width: 40 }] : []),
{
title: t.value.threat.threatCode,
key: 'code',
width: 160,
ellipsis: false,
titleStyle: { whiteSpace: 'nowrap' },
},
{
title: t.value.threat.threatDefinition,
key: 'threat_definition',
minWidth: 300,
titleStyle: { whiteSpace: 'nowrap' },
render: row => {
const agent = row.threat_agent?.trim()
const action = row.adverse_action?.trim()
const assetsText = row.assets_affected?.trim() || row.linked_assets.map(item => item.name).join(', ')
if (!agent && !action) return h('span', { style: 'color:#aaa' }, '-')
// Build natural-language sentence
const parts: string[] = []
if (agent && action) {
parts.push(`${agent} may be able to ${action.charAt(0).toLowerCase() + action.slice(1)}`)
} else if (action) {
parts.push(action)
} else if (agent) {
parts.push(agent)
}
if (assetsText) {
parts.push(`affecting ${assetsText}`)
}
const sentence = parts.join(', ') + '.'
return h('span', { style: 'display:block; line-height:1.7; padding:4px 0; word-break:break-word' }, sentence)
},
},
{
title: t.value.threat.linkedAssets,
key: 'linked_assets',
width: 220,
render: row => {
const hasAsset = row.linked_assets?.length > 0
if (!hasAsset) {
  return h(NTooltip, {
    placement: 'top',
    trigger: 'hover',
  }, {
    default: () => 'Asset is required',
    trigger: () => h(NIcon, { size: 20, color: '#d43f3a' }, () => h(AlertCircleOutline)),
  })
}
return h(NSpace, { size: 'small', wrap: true }, () => row.linked_assets.map(asset =>
  h(NButton, {
    size: 'tiny',
    tertiary: true,
    onClick: () => goToAsset(asset.id),
  }, () => asset.name)
))
},
},
{
title: t.value.threat.linkedObjectives,
key: 'linked_objectives',
width: 240,
render: row => {
const linkedObjectives = threatObjectiveMap.value[row.id] ?? []
if (!linkedObjectives.length) {
  return h(NTooltip, {
    placement: 'top',
    trigger: 'hover',
  }, {
    default: () => 'Objective is required',
    trigger: () => h(NIcon, { size: 20, color: '#d43f3a' }, () => h(AlertCircleOutline)),
  })
}
return h(NSpace, { size: 'small', wrap: true }, () => linkedObjectives.map(objective =>
  h(NButton, {
    size: 'tiny',
    tertiary: true,
    onClick: () => goToObjective(objective.id),
  }, () => objective.code)
))
},
},
{
title: t.value.threat.reviewStatus,
key: 'review_status',
width: 120,
titleStyle: { whiteSpace: 'nowrap' },
render: row => h(NTag, { type: statusTagType(row.review_status), size: 'small' }, () => statusLabel(row.review_status)),
},
{
  title: t.value.common.actions,
  key: 'actions',
  fixed: 'right',
  width: 140,
  titleStyle: { whiteSpace: 'nowrap' },
  render: row =>
    h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openDrawer(row) }, () => t.value.common.edit),
      ...(canWrite.value ? [
        h(NButton, {
          size: 'tiny',
          text: true,
          type: 'primary',
          disabled: row.review_status === 'confirmed',
          onClick: () => confirmSingle(row),
        }, () => t.value.threat.confirmThreat),
        h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => deleteSingle(row) }, () => t.value.common.delete),
      ] : []),
    ]),
},
])

// ── Add threat ──
const addDrawerVisible = ref(false)
const addLoading = ref(false)
const addForm = ref({
code: '',
definition: '',
asset_ids: [] as string[],
objective_ids: [] as string[],
})

function openAddDrawer() {
addForm.value = { code: '', definition: '', asset_ids: [], objective_ids: [] }
addDrawerVisible.value = true
}

async function submitAddThreat() {
if (!addForm.value.code.trim()) {
message.warning(t.value.threat.threatCode + ' is required')
return
}
addLoading.value = true
try {
const payload = {
code: addForm.value.code.trim(),
adverse_action: addForm.value.definition.trim(),
asset_ids: addForm.value.asset_ids,
}
const res = await threatApi.createThreat(props.toeId, payload)
await syncThreatObjectives(res.data.id, addForm.value.objective_ids)
message.success(t.value.common.success)
addDrawerVisible.value = false
emit('refresh')
} catch (e: any) {
message.error(e.message)
} finally {
addLoading.value = false
}
}

// ── Edit drawer ──
const drawerVisible = ref(false)
const drawerThreat: Ref<Threat | null> = ref(null)
const saveLoading = ref(false)
const overrideRiskLevel = ref<string | null>(null)

const editForm = ref({
code: '',
definition: '',
asset_ids: [] as string[],
objective_ids: [] as string[],
ai_rationale: '',
ai_source_ref: '',
})
const aiRationaleDisplay = computed(() => {
const raw = editForm.value.ai_rationale || ''
return raw
})

function buildThreatDefinitionText(t: Threat): string {
const agent = t.threat_agent?.trim()
const action = t.adverse_action?.trim()
const assetsText = t.assets_affected?.trim() || t.linked_assets?.map((item: any) => item.name).join(', ')
if (!agent && !action) return ''
const parts: string[] = []
if (agent && action) {
parts.push(`${agent} may be able to ${action.charAt(0).toLowerCase() + action.slice(1)}`)
} else if (action) {
parts.push(action)
} else if (agent) {
parts.push(agent)
}
if (assetsText) {
parts.push(`affecting ${assetsText}`)
}
return parts.join(', ') + '.'
}

function openDrawer(t: Threat) {
drawerThreat.value = t
const linkedObjectiveIds = (threatObjectiveMap.value[t.id] ?? []).map(item => item.id)
editForm.value = {
code: t.code,
definition: buildThreatDefinitionText(t),
asset_ids: t.asset_ids ?? [],
objective_ids: linkedObjectiveIds,
ai_rationale: t.ai_rationale ?? '',
ai_source_ref: t.ai_source_ref ?? '',
}
overrideRiskLevel.value = t.risk_overridden ? t.risk_level : null
drawerVisible.value = true
}

function goToAsset(assetId: string) {
  router.push({ name: 'TOEDetail', params: { id: props.toeId }, query: { tab: 'assets', focusAssetId: assetId } })
}

function goToObjective(objectiveId: string) {
  router.push({ name: 'Security', query: { toeId: props.toeId, tab: 'objectives', focusObjectiveId: objectiveId } })
}

async function syncThreatObjectives(threatId: string, nextObjectiveIds: string[]) {
  const currentObjectiveIds = (threatObjectiveMap.value[threatId] ?? []).map(item => item.id)
  const toAdd = nextObjectiveIds.filter(id => !currentObjectiveIds.includes(id))
  const toRemove = currentObjectiveIds.filter(id => !nextObjectiveIds.includes(id))

  await Promise.all(toAdd.map(objectiveId =>
    securityApi.addSourceMapping(props.toeId, objectiveId, 'threat', threatId)
  ))
  await Promise.all(toRemove.map(objectiveId =>
    securityApi.removeSourceMapping(props.toeId, objectiveId, 'threat', threatId)
  ))
}

function handleFocusedThreat() {
  const focusThreatId = typeof route.query.focusThreatId === 'string' ? route.query.focusThreatId : null
  if (!focusThreatId) return
  const threat = props.threats.find(item => item.id === focusThreatId)
  if (!threat) return
  openDrawer(threat)
  router.replace({ query: { ...route.query, focusThreatId: undefined } })
}

async function saveThreat() {
if (!drawerThreat.value) return
saveLoading.value = true
try {
// Parse definition back - try to extract from natural language or keep as structured
const payload: any = { code: editForm.value.code }
const defText = editForm.value.definition
const lines = defText.split('\n').map(s => s.trim()).filter(s => s)
// Try to extract the three components
let hasAgent = false, hasAction = false, hasAssets = false
let agent = '', action = '', assets = ''
for (let i = 0; i < lines.length; i++) {
if (lines[i].includes('may be able to')) {
const match = lines[i].match(/^(.+?)\s+may be able to\s+(.+?)(?:\s*,|$)/)
if (match) {
agent = match[1].trim()
action = match[2].trim()
if (action.endsWith('.')) action = action.slice(0, -1)
hasAgent = true
hasAction = true
}
}
if (lines[i].includes('affecting')) {
const match = lines[i].match(/affecting\s+(.+?)\.?\s*$/)
if (match) {
assets = match[1].trim()
hasAssets = true
}
}
}
// If parsing failed, keep default values unless user explicitly set them
payload.threat_agent = agent || drawerThreat.value.threat_agent || ''
payload.adverse_action = action || drawerThreat.value.adverse_action || ''
payload.assets_affected = assets || drawerThreat.value.assets_affected || ''
payload.asset_ids = editForm.value.asset_ids
payload.ai_rationale = editForm.value.ai_rationale
payload.ai_source_ref = editForm.value.ai_source_ref
if (overrideRiskLevel.value) {
await threatApi.overrideRisk(props.toeId, drawerThreat.value.id, overrideRiskLevel.value)
}
await threatApi.updateThreat(props.toeId, drawerThreat.value.id, payload)
await syncThreatObjectives(drawerThreat.value.id, editForm.value.objective_ids)
message.success(t.value.common.success)
drawerVisible.value = false
emit('refresh')
} catch (e: any) {
message.error(e.message)
} finally {
saveLoading.value = false
}
}

async function confirmSingle(threat?: Threat) {
const target = threat || drawerThreat.value
if (!target) return
try {
await threatApi.confirmThreat(props.toeId, target.id)
message.success(t.value.threat.statusConfirmed)
if (!threat) drawerVisible.value = false
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function falsePositiveSingle() {
if (!drawerThreat.value) return
try {
await threatApi.falsePositiveThreat(props.toeId, drawerThreat.value.id)
message.success(t.value.threat.statusFalsePositive)
drawerVisible.value = false
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function revertSingle() {
if (!drawerThreat.value) return
try {
await threatApi.revertThreat(props.toeId, drawerThreat.value.id)
message.success(t.value.threat.statusPending)
drawerVisible.value = false
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

// ── Batch actions ──
async function batchConfirm() {
batchConfirming.value = true
try {
const res = await threatApi.batchConfirm(props.toeId, checkedRowKeys.value)
message.success(`${t.value.threat.statusConfirmed} ${res.data.updated}`)
checkedRowKeys.value = []
emit('refresh')
} catch (e: any) { message.error(e.message) }
finally { batchConfirming.value = false }
}

async function batchDelete() {
batchDeleting.value = true
try {
const res = await threatApi.batchDelete(props.toeId, checkedRowKeys.value)
message.success(`${t.value.common.delete} ${res.data.deleted}`)
checkedRowKeys.value = []
emit('refresh')
} catch (e: any) { message.error(e.message) }
finally { batchDeleting.value = false }
}

async function deleteSingle(row: Threat) {
try {
await threatApi.deleteThreat(props.toeId, row.id)
message.success(t.value.common.success)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function loadAssets() {
try {
const res = await toeApi.listAssets(props.toeId)
assets.value = res.data
} catch (e: any) {
message.error(e.message)
}
}

// ── AI scanning ──
const scanModalVisible = ref(false)
const scanTaskId = ref<string | null>(null)
const scanProgress = ref(0)
const scanStatusMsg = ref(t.value.threat.initTask)
const scanFailed = ref(false)
let scanTimer: ReturnType<typeof setInterval> | null = null

async function handleAiScan() {
// Auto mode: full scan when no threats, incremental when threats exist
const mode = props.threats.length === 0 ? 'full' : 'incremental'
scanModalVisible.value = true
scanProgress.value = 0
scanStatusMsg.value = t.value.threat.initTask
scanFailed.value = false
try {
const res = await threatApi.aiScan(props.toeId, mode, localeStore.lang)
scanTaskId.value = res.data.task_id
startScanPolling()
} catch (e: any) {
scanStatusMsg.value = `${t.value.threat.submitFailed}: ${e.message}`
scanFailed.value = true
}
}

function startScanPolling() {
scanTimer = setInterval(async () => {
if (!scanTaskId.value) return
try {
const res = await taskApi.get(scanTaskId.value)
const task = res.data
if (task.status === 'done') {
scanProgress.value = 100
scanStatusMsg.value = translateScanProgress(task.result_summary) ?? t.value.threat.scanComplete
stopScanPolling()
emit('refresh')
} else if (task.status === 'failed') {
scanProgress.value = 0
scanStatusMsg.value = `${t.value.threat.scanFailed}: ${task.error_message ?? t.value.common.error}`
scanFailed.value = true
stopScanPolling()
} else {
scanProgress.value = Math.min(scanProgress.value + 5, 90)
scanStatusMsg.value = translateScanProgress(task.progress_message)
}
} catch (_) { /* ignore polling errors */ }
}, 2000)
}

function translateScanProgress(msg: string | null): string {
if (!msg) return t.value.threat.processing

const progressMap: Record<string, string> = {
  'Stage 1/4: Preparing scan...': 'Stage 1/4: Preparing scan...',
  'Stage 1/4: Reading TOE information...': 'Stage 1/4: Reading TOE information...',
  'Stage 2/4: Reading document content...': 'Stage 2/4: Reading document content...',
  'Stage 3/4: AI identifying threats...': 'Stage 3/4: AI identifying threats...',
}

if (progressMap[msg]) return progressMap[msg]

const writeStageEn = msg.match(/^Stage 4\/4: Writing\s+(\d+)\s+candidate threats\.\.\.$/)
if (writeStageEn) {
  return `Stage 4/4: Writing ${writeStageEn[1]} candidate threats...`
}

const incrementalAddedEn = msg.match(/^Incremental scan completed, added\s+(\d+)\s+candidate threats$/)
if (incrementalAddedEn) {
  return `Incremental scan completed, added ${incrementalAddedEn[1]} candidate threats`
}

if (msg === 'Incremental scan completed, no new threats found') {
  return msg
}

const fullAddedEn = msg.match(/^Full scan completed, identified\s+(\d+)\s+candidate threats$/)
if (fullAddedEn) {
  return `Full scan completed, identified ${fullAddedEn[1]} candidate threats`
}

return msg
}

function stopScanPolling() {
if (scanTimer) { clearInterval(scanTimer); scanTimer = null }
}

function closeScanModal() {
stopScanPolling()
scanModalVisible.value = false
scanTaskId.value = null
scanProgress.value = 0
}

// cleanup
import { onUnmounted } from 'vue'
onUnmounted(stopScanPolling)

// ── Threat Import from ST/PP docs ──
const importLoading = ref(false)
const importModalVisible = ref(false)
const importTaskId = ref<string | null>(null)
const importProgress = ref(0)
const importStatusMsg = ref('')
const importFailed = ref(false)
const importStage = ref<'confirm' | 'progress'>('confirm')
const importFiles = ref<any[]>([])
const importRunning = ref(false)
let importTimer: ReturnType<typeof setInterval> | null = null

async function handleImport() {
importLoading.value = true
try {
const res = await toeApi.listFiles(props.toeId, 'st_pp')
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
// Show file list for user confirmation
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
importStage.value = 'progress'
importProgress.value = 0
importStatusMsg.value = t.value.threat.initTask
const taskRes = await threatApi.importFromDocs(props.toeId)
importTaskId.value = taskRes.data.task_id
startImportPolling()
} catch (e: any) {
importStatusMsg.value = `${t.value.threat.submitFailed}: ${e.message}`
importFailed.value = true
} finally {
importRunning.value = false
}
}

function translateProgress(msg: string | null): string {
if (!msg) return t.value.threat.processing
const progressMap: Record<string, string> = {
'threat_import.stage_1': t.value.threat.importStage1,
'threat_import.stage_2': t.value.threat.importStage2,
'threat_import.stage_3': t.value.threat.importStage3,
}
if (progressMap[msg]) return progressMap[msg]
// result summary: "threat_import.done|totalT|totalA|totalO|newT|newA|newO"
if (msg.startsWith('threat_import.done|')) {
const parts = msg.split('|')
return t.value.threat.importDone
  .replace('{totalThreats}', parts[1] ?? '0')
  .replace('{totalAssumptions}', parts[2] ?? '0')
  .replace('{totalOsps}', parts[3] ?? '0')
  .replace('{newThreats}', parts[4] ?? '0')
  .replace('{newAssumptions}', parts[5] ?? '0')
  .replace('{newOsps}', parts[6] ?? '0')
}
return msg
}

function startImportPolling() {
importTimer = setInterval(async () => {
if (!importTaskId.value) return
try {
const res = await taskApi.get(importTaskId.value)
const task = res.data
if (task.status === 'done') {
importProgress.value = 100
importStatusMsg.value = translateProgress(task.result_summary)
stopImportPolling()
emit('refresh')
} else if (task.status === 'failed') {
importProgress.value = 0
importStatusMsg.value = `${t.value.threat.scanFailed}: ${task.error_message ?? ''}`
importFailed.value = true
stopImportPolling()
} else {
importProgress.value = Math.min(importProgress.value + 8, 90)
importStatusMsg.value = translateProgress(task.progress_message)
}
} catch (_) { /* ignore */ }
}, 2000)
}

function stopImportPolling() {
if (importTimer) { clearInterval(importTimer); importTimer = null }
}

function closeImportModal() {
stopImportPolling()
importModalVisible.value = false
importTaskId.value = null
importProgress.value = 0
}

onUnmounted(stopImportPolling)

watch(() => props.toeId, () => {
loadAssets()
})

watch(() => props.threats, () => {
handleFocusedThreat()
}, { deep: true })

watch(() => route.query.focusThreatId, () => {
handleFocusedThreat()
})

onMounted(() => {
loadAssets()
handleFocusedThreat()
})
</script>