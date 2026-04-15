<template>
<div>
<n-space justify="space-between" style="margin-bottom: 12px">
<n-space>
<n-select
v-model:value="filterType"
:options="typeOptions"
:placeholder="t.security.filterType"
clearable
style="width: 130px"
/>
<n-select
v-model:value="filterStatus"
:options="statusOptions"
:placeholder="t.security.filterStatus"
clearable
style="width: 140px"
/>
</n-space>
<n-space>
<template v-if="canWrite && checkedRowKeys.length > 0">
<n-button size="small" :loading="batchConfirming" @click="batchConfirm">{{ t.common.confirm }} ({{ checkedRowKeys.length }})</n-button>
<n-button size="small" :loading="batchDeleting" @click="batchDelete">{{ t.common.delete }} ({{ checkedRowKeys.length }})</n-button>
</template>
<slot name="actions" />
</n-space>
</n-space>

<n-data-table
:columns="columns"
:data="filteredObjectives"
:loading="loading"
:row-key="(row: SecurityObjective) => row.id"
v-model:checked-row-keys="checkedRowKeys"
size="small"
/>

<!-- Add / edit drawer -->
<n-drawer v-model:show="drawerVisible" :width="500" placement="right">
<n-drawer-content :title="editItem ? `${t.security.editObjective} ${editItem.code}` : t.security.addObjective" closable>
<n-form :model="editForm" label-placement="top" size="small" :disabled="!canWrite">
<n-grid :cols="2" :x-gap="12">
<n-form-item-gi :label="t.security.objectiveCode">
<n-input v-model:value="editForm.code" placeholder="O.AUTH_CONTROL" />
</n-form-item-gi>
<n-form-item-gi :label="t.security.objectiveType">
<n-radio-group v-model:value="editForm.obj_type">
<n-radio value="O">{{ t.security.typeO }}</n-radio>
<n-radio value="OE">{{ t.security.typeOE }}</n-radio>
</n-radio-group>
</n-form-item-gi>
</n-grid>
<n-form-item :label="t.common.description">
<n-input v-model:value="editForm.description" type="textarea" :rows="4" />
</n-form-item>
<n-form-item :label="t.security.rationale">
<n-input v-model:value="editForm.rationale" type="textarea" :rows="3" />
</n-form-item>
<n-form-item>
<template #label>{{ t.security.linkedSfrs }}</template>
<n-select
v-model:value="editForm.sfr_ids"
:options="sfrOptions"
multiple
clearable
filterable
:placeholder="t.security.selectSfrs"
 />
</n-form-item>
<n-form-item :label="t.security.linkedThreats">
<n-select
v-model:value="editForm.threat_ids"
:options="threatOptions"
multiple
clearable
filterable
:placeholder="t.security.selectThreats"
 />
</n-form-item>
<n-form-item :label="t.security.linkedAssumptions">
<n-select
v-model:value="editForm.assumption_ids"
:options="assumptionOptions"
multiple
clearable
filterable
:placeholder="t.security.selectAssumptions"
 />
</n-form-item>
<n-form-item :label="t.security.linkedOsps">
<n-select
v-model:value="editForm.osp_ids"
:options="ospOptions"
multiple
clearable
filterable
:placeholder="t.security.selectOsps"
 />
</n-form-item>
</n-form>
<n-divider />
<n-space justify="end">
<n-button @click="drawerVisible = false">{{ t.common.cancel }}</n-button>
<n-button v-if="canWrite" type="primary" :loading="saveLoading" @click="saveItem">{{ t.common.save }}</n-button>
</n-space>
</n-drawer-content>
</n-drawer>

<!-- AI progress modal -->
<n-modal v-model:show="aiModalVisible" :mask-closable="false" preset="card" :title="t.security.aiGenerateObjectives" style="width: 440px">
<div style="text-align: center; padding: 16px 0">
<n-progress type="line" :percentage="aiProgress" :indicator-placement="'inside'" style="margin-bottom: 16px" />
<p style="color: #666; font-size: 13px">{{ aiStatusMsg }}</p>
</div>
<template #footer>
<n-button :disabled="aiProgress < 100 && !aiFailed" @click="closeAiModal">
{{ aiProgress >= 100 || aiFailed ? t.threat.complete : t.threat.runInBackground }}
</n-button>
</template>
</n-modal>
</div>
</template>

<script setup lang="ts">
import { ref, computed, h, onUnmounted, watch, type ComputedRef, type Ref } from 'vue'
import { useMessage, NButton, NTag, NSpace } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { securityApi } from '@/api/security'
import { taskApi } from '@/api/tasks'
import type { SecurityObjective, ObjectiveSources, SFRInstance } from '@/api/security'
import type { Threat, Assumption, OSP } from '@/api/threats'
import type { DataTableColumns, DataTableRowKey } from 'naive-ui'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))

const props = defineProps<{
toeId: string
objectives: SecurityObjective[]
threats: Threat[]
assumptions: Assumption[]
osps: OSP[]
sfrs: SFRInstance[]
objectiveSourcesMap: Record<string, ObjectiveSources>
loading: boolean
canWrite: boolean
}>()
const emit = defineEmits<{ (e: 'refresh'): void }>()
const message = useMessage()
const route = useRoute()
const router = useRouter()
const canWrite = computed(() => props.canWrite)

const editForm = ref({
code: '',
obj_type: 'O',
description: '',
rationale: '',
sfr_ids: [] as string[],
threat_ids: [] as string[],
assumption_ids: [] as string[],
osp_ids: [] as string[],
})

const filterType = ref<string | null>(null)
const filterStatus = ref<string | null>(null)
const typeOptions = computed(() => [
{ label: t.value.security.typeO, value: 'O' },
{ label: t.value.security.typeOE, value: 'OE' },
])
const statusOptions = computed(() => [
{ label: t.value.security.draft, value: 'draft' },
{ label: t.value.security.confirmed, value: 'confirmed' },
{ label: t.value.security.rejected, value: 'rejected' },
])
const threatOptions = computed(() => props.threats.map(item => ({ label: item.code, value: item.id })))
const assumptionOptions = computed(() => editForm.value.obj_type === 'OE'
	? props.assumptions.map(item => ({ label: item.code, value: item.id }))
	: [])
const ospOptions = computed(() => props.osps.map(item => ({ label: item.code, value: item.id })))
const sfrOptions = computed(() => props.sfrs.map(item => ({ label: item.sfr_id, value: item.id })))
const threatCodeMap = computed(() => new Map(props.threats.map(item => [item.id, item.code] as const)))
const assumptionCodeMap = computed(() => new Map(props.assumptions.map(item => [item.id, item.code] as const)))
const ospCodeMap = computed(() => new Map(props.osps.map(item => [item.id, item.code] as const)))

const filteredObjectives = computed(() => {
let list = props.objectives
if (filterType.value) list = list.filter(o => o.obj_type === filterType.value)
if (filterStatus.value) list = list.filter(o => o.review_status === filterStatus.value)
return list
})

const objectiveSfrMap = computed(() => {
	const mapping: Record<string, string[]> = {}
	for (const sfr of props.sfrs) {
		for (const objective of sfr.linked_objectives ?? []) {
			if (!mapping[objective.id]) {
				mapping[objective.id] = []
			}
			const label = sfr.sfr_id || sfr.library?.sfr_component || '-'
			if (!mapping[objective.id].includes(label)) {
				mapping[objective.id].push(label)
			}
		}
	}
	return mapping
})

const objectiveSfrIdMap = computed(() => {
	const mapping: Record<string, string[]> = {}
	for (const sfr of props.sfrs) {
		for (const objective of sfr.linked_objectives ?? []) {
			if (!mapping[objective.id]) {
				mapping[objective.id] = []
			}
			if (!mapping[objective.id].includes(sfr.id)) {
				mapping[objective.id].push(sfr.id)
			}
		}
	}
	return mapping
})

function localizedImportedRationale() {
	return t.value.security.importedFromStPpRationale ?? 'Imported from ST/PP document'
}

function normalizeRationaleForDisplay(value: string | null | undefined) {
	const normalized = (value ?? '').trim()
	if (!normalized) return ''
	if (
		normalized === 'Imported from ST/PP document' ||
		normalized === 'st_pp_imported'
	) {
		return localizedImportedRationale()
	}
	return normalized
}

function normalizeRationaleForSave(value: string | null | undefined) {
	const normalized = (value ?? '').trim()
	if (!normalized) return ''
	if (normalized === localizedImportedRationale()) {
		return 'st_pp_imported'
	}
	return normalized
}

function statusTagType(s: string) {
return s === 'confirmed' ? 'success' : s === 'rejected' ? 'error' : 'default'
}
function statusLabel(s: string) {
return s === 'confirmed' ? t.value.security.confirmed : s === 'rejected' ? t.value.security.rejected : t.value.security.draft
}

function objectiveSourceButtons(objectiveId: string) {
const sources = props.objectiveSourcesMap[objectiveId] ?? { threat_ids: [], assumption_ids: [], osp_ids: [] }
return [
	...sources.threat_ids.flatMap(id => {
		const label = threatCodeMap.value.get(id)
		return label ? [{ type: 'threat' as const, id, label }] : []
	}),
	...sources.assumption_ids.flatMap(id => {
		const label = assumptionCodeMap.value.get(id)
		return label ? [{ type: 'assumption' as const, id, label }] : []
	}),
	...sources.osp_ids.flatMap(id => {
		const label = ospCodeMap.value.get(id)
		return label ? [{ type: 'osp' as const, id, label }] : []
	}),
]
}

function goToSource(type: 'threat' | 'assumption' | 'osp', id: string) {
	const tab = type === 'threat' ? 'threats' : type === 'assumption' ? 'assumptions' : 'osps'
	const focusKey = type === 'threat' ? 'focusThreatId' : type === 'assumption' ? 'focusAssumptionId' : 'focusOspId'
	router.push({ name: 'Threats', query: { toeId: props.toeId, tab, [focusKey]: id } })
}

async function syncObjectiveSources(objectiveId: string, nextSources: { threat_ids: string[]; assumption_ids: string[]; osp_ids: string[] }) {
	const currentSources = props.objectiveSourcesMap[objectiveId] ?? { threat_ids: [], assumption_ids: [], osp_ids: [] }
	const sourceTypes: Array<'threat' | 'assumption' | 'osp'> = ['threat', 'assumption', 'osp']

	for (const sourceType of sourceTypes) {
		const key = `${sourceType}_ids` as 'threat_ids' | 'assumption_ids' | 'osp_ids'
		const currentIds = currentSources[key] ?? []
		const nextIds = nextSources[key] ?? []
		const toAdd = nextIds.filter(id => !currentIds.includes(id))
		const toRemove = currentIds.filter(id => !nextIds.includes(id))

		await Promise.all(toAdd.map(sourceId =>
			securityApi.addSourceMapping(props.toeId, objectiveId, sourceType, sourceId)
		))
		await Promise.all(toRemove.map(sourceId =>
			securityApi.removeSourceMapping(props.toeId, objectiveId, sourceType, sourceId)
		))
	}
}

async function syncObjectiveSfrs(objectiveId: string, nextSfrIds: string[]) {
	const currentSfrIds = objectiveSfrIdMap.value[objectiveId] ?? []
	const toAdd = nextSfrIds.filter(id => !currentSfrIds.includes(id))
	const toRemove = currentSfrIds.filter(id => !nextSfrIds.includes(id))

	await Promise.all(toAdd.map(sfrId =>
		securityApi.addObjectiveSFR(props.toeId, objectiveId, sfrId, normalizeRationaleForSave(editForm.value.rationale) || undefined)
	))
	await Promise.all(toRemove.map(sfrId =>
		securityApi.removeObjectiveSFR(props.toeId, objectiveId, sfrId)
	))
}

function handleFocusedObjective() {
	const focusObjectiveId = typeof route.query.focusObjectiveId === 'string' ? route.query.focusObjectiveId : null
	if (!focusObjectiveId) return
	const objective = props.objectives.find(item => item.id === focusObjectiveId)
	if (!objective) return
	openEdit(objective)
	router.replace({ query: { ...route.query, focusObjectiveId: undefined } })
}

watch(() => editForm.value.obj_type, value => {
	if (value !== 'OE' && editForm.value.assumption_ids.length > 0) {
		editForm.value.assumption_ids = []
	}
})

const checkedRowKeys = ref<DataTableRowKey[]>([])
const batchConfirming = ref(false)
const batchDeleting = ref(false)

type ObjCols = DataTableColumns<SecurityObjective>
const columns: ComputedRef<ObjCols> = computed(() => [
...(canWrite.value ? [{ type: 'selection' as const, width: 44 }] : []),
{
title: t.value.security.objectiveCode,
key: 'code',
width: 180,
render: row => h('div', {}, row.code),
},
{
title: t.value.security.objectiveDefinition,
key: 'description',
minWidth: 260,
render: row => row.description ?? '-',
},
{
title: t.value.security.linkedSecurityProblems,
key: 'linked_sources',
minWidth: 220,
render: row => {
const linkedSources = objectiveSourceButtons(row.id)
if (!linkedSources.length) return h('span', { style: 'color:#999' }, '-')
return h(NSpace, { size: 'small', wrap: true }, () => linkedSources.map(source =>
	h(NButton, {
		size: 'tiny',
		tertiary: true,
		onClick: () => goToSource(source.type, source.id),
	}, () => source.label)
))
},
},
{
title: t.value.security.linkedSfrs,
key: 'linked_sfrs',
minWidth: 220,
render: row => {
	const linkedSfrs = objectiveSfrMap.value[row.id] ?? []
	if (!linkedSfrs.length) return h('span', { style: 'color:#999' }, '-')
	return h(NSpace, { size: 'small', wrap: true }, () => linkedSfrs.map(sfrId =>
		h(NTag, { size: 'small', type: 'info' }, () => sfrId)
	))
},
},
{
 title: t.value.threat.reviewStatus,
key: 'review_status',
width: 120,
render: row => h(NTag, { type: statusTagType(row.review_status), size: 'small' }, () => statusLabel(row.review_status)),
},
{
 title: t.value.toe.operation,
key: 'actions',
width: 170,
render: row =>
h(NSpace, { size: 4 }, () => [
h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, () => t.value.common.edit),
...(canWrite.value ? [
	h(NButton, {
	size: 'tiny',
	disabled: row.review_status === 'confirmed',
	onClick: () => confirmItem(row),
	}, () => t.value.common.confirm),
	h(NButton, { size: 'tiny', onClick: () => deleteItem(row) }, () => t.value.common.delete),
] : []),
]),
},
])

// ── Drawer ──
const drawerVisible = ref(false)
const editItem: Ref<SecurityObjective | null> = ref(null)
const saveLoading = ref(false)

function openAdd() {
editItem.value = null
editForm.value = { code: '', obj_type: 'O', description: '', rationale: '', sfr_ids: [], threat_ids: [], assumption_ids: [], osp_ids: [] }
drawerVisible.value = true
}

function openEdit(item: SecurityObjective) {
const linkedSources = props.objectiveSourcesMap[item.id] ?? { threat_ids: [], assumption_ids: [], osp_ids: [] }
editItem.value = item
editForm.value = {
code: item.code,
obj_type: item.obj_type,
description: item.description ?? '',
rationale: normalizeRationaleForDisplay(item.rationale),
	sfr_ids: [...(objectiveSfrIdMap.value[item.id] ?? [])],
threat_ids: [...linkedSources.threat_ids],
assumption_ids: [...linkedSources.assumption_ids],
osp_ids: [...linkedSources.osp_ids],
}
drawerVisible.value = true
}

async function saveItem() {
if (
	editForm.value.threat_ids.length === 0 &&
	editForm.value.assumption_ids.length === 0 &&
	editForm.value.osp_ids.length === 0
) {
	message.warning(t.value.security.atLeastOneSource)
	return
}
saveLoading.value = true
try {
const payload = {
	...editForm.value,
	rationale: normalizeRationaleForSave(editForm.value.rationale),
}
if (editItem.value) {
await securityApi.updateObjective(props.toeId, editItem.value.id, payload)
await syncObjectiveSources(editItem.value.id, payload)
await syncObjectiveSfrs(editItem.value.id, editForm.value.sfr_ids)
message.success(t.value.common.success)
} else {
const res = await securityApi.createObjective(props.toeId, payload)
await syncObjectiveSources(res.data.id, payload)
await syncObjectiveSfrs(res.data.id, editForm.value.sfr_ids)
message.success(t.value.common.success)
}
drawerVisible.value = false
emit('refresh')
} catch (e: any) {
message.error(e.message)
} finally {
saveLoading.value = false
}
}

async function deleteItem(item: SecurityObjective) {
try {
await securityApi.deleteObjective(props.toeId, item.id)
message.success(t.value.common.success)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function confirmItem(item: SecurityObjective) {
try {
await securityApi.confirmObjective(props.toeId, item.id)
message.success(t.value.security.confirmed)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function batchConfirm() {
batchConfirming.value = true
try {
	for (const id of checkedRowKeys.value) {
		await securityApi.confirmObjective(props.toeId, id as string)
	}
	message.success(`${t.value.common.confirm} ${checkedRowKeys.value.length}`)
	checkedRowKeys.value = []
	emit('refresh')
} catch (e: any) {
	message.error(e.message)
	} finally {
		batchConfirming.value = false
}
}

async function batchDelete() {
batchDeleting.value = true
try {
	for (const id of checkedRowKeys.value) {
		await securityApi.deleteObjective(props.toeId, id as string)
	}
	message.success(`${t.value.common.delete} ${checkedRowKeys.value.length}`)
	checkedRowKeys.value = []
	emit('refresh')
} catch (e: any) {
	message.error(e.message)
} finally {
	batchDeleting.value = false
}
}

// ── AI generation ──
const aiDropdownOptions = computed(() => [
{ label: t.value.security.fullGenerate, key: 'full' },
{ label: t.value.security.incrementalGenerate, key: 'incremental' },
])
const aiLoading = ref(false)
const aiModalVisible = ref(false)
const aiProgress = ref(0)
const aiStatusMsg = ref(t.value.threat.initTask)
const aiFailed = ref(false)
const aiTaskId = ref<string | null>(null)
let aiTimer: ReturnType<typeof setInterval> | null = null

function translateObjectiveProgress(msg: string | null): string {
if (!msg) return t.value.threat.processing
if (msg === 'Stage 1/4: Reading TOE information...') {
return t.value.security.objectiveAiStageReadToe
}
if (msg === 'Stage 2/4: Preparing AI context...') {
return t.value.security.objectiveAiStagePrepare
}
if (msg === 'Stage 3/4: AI generating security objectives...') {
return t.value.security.objectiveAiStageGenerate
}
const writingMatch = msg.match(/^Stage 4\/4: Writing\s+(\d+)\s+security objectives\.\.\.$/)
if (writingMatch) {
const count = writingMatch[1] ?? '0'
return t.value.security.objectiveAiStageWrite.replace('{count}', count)
}
const completeMatch = msg.match(/^Objective generation complete, added\s+(\d+)\s+objectives$/)
if (completeMatch) {
const count = completeMatch[1] ?? '0'
return t.value.security.objectiveAiDone.replace('{count}', count)
}
return msg
}

function resolveAiProgress(msg: string | null, status: string): number {
if (status === 'done') return 100
if (!msg) return 0
if (msg === 'Stage 1/4: Reading TOE information...') return 20
if (msg === 'Stage 2/4: Preparing AI context...') return 45
if (msg === 'Stage 3/4: AI generating security objectives...') return 75
if (/^Stage 4\/4: Writing\s+\d+\s+security objectives\.\.\.$/.test(msg)) return 92
return Math.min(aiProgress.value + 5, 90)
}

async function startAiGenerate(key: string = 'incremental') {
aiModalVisible.value = true
aiProgress.value = 0
aiStatusMsg.value = t.value.threat.initTask
aiFailed.value = false
aiLoading.value = true
try {
const res = await securityApi.aiGenerateObjectives(props.toeId, key, localeStore.lang)
aiTaskId.value = res.data.task_id
aiTimer = setInterval(async () => {
if (!aiTaskId.value) return
try {
const task = (await taskApi.get(aiTaskId.value)).data
if (task.status === 'done') {
aiProgress.value = 100
aiStatusMsg.value = translateObjectiveProgress(task.result_summary ?? t.value.threat.scanComplete)
clearInterval(aiTimer!); aiTimer = null
emit('refresh')
} else if (task.status === 'failed') {
aiProgress.value = 0
 aiStatusMsg.value = `${t.value.threat.scanFailed}: ${task.error_message ?? t.value.common.error}`
aiFailed.value = true
clearInterval(aiTimer!); aiTimer = null
} else {
aiProgress.value = resolveAiProgress(task.progress_message, task.status)
aiStatusMsg.value = translateObjectiveProgress(task.progress_message)
}
} catch (_) {}
}, 2000)
} catch (e: any) {
aiStatusMsg.value = `${t.value.threat.submitFailed}: ${e.message}`
aiFailed.value = true
} finally {
aiLoading.value = false
}
}

async function handleAiSelect(key: string) {
await startAiGenerate(key)
}

function closeAiModal() {
if (aiTimer) { clearInterval(aiTimer); aiTimer = null }
aiModalVisible.value = false
}

watch(() => props.objectives, () => {
	handleFocusedObjective()
}, { deep: true })

watch(() => route.query.focusObjectiveId, () => {
	handleFocusedObjective()
})

onUnmounted(() => { if (aiTimer) clearInterval(aiTimer) })

defineExpose({ openAdd, startAiGenerate })
</script>