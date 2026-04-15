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
</n-space>
<n-space>
<template v-if="canWrite && checkedKeys.length > 0">
<n-button size="small" :loading="batchConfirming" @click="batchConfirm">
{{ t.threat.confirmThreat }} ({{ checkedKeys.length }})
</n-button>
<n-button size="small" :loading="batchDeleting" @click="batchDelete">
{{ t.common.delete }} ({{ checkedKeys.length }})
</n-button>
</template>
<n-button v-if="canWrite" @click="openAiSuggest" :loading="aiLoading">{{ t.threat.aiSuggestion }}</n-button>
<n-button v-if="canWrite" @click="openAdd">+ {{ props.itemType === 'assumption' ? t.threat.addAssumption : t.threat.addOsp }}</n-button>
</n-space>
</n-space>

<!-- List -->
<n-data-table
:columns="columns"
:data="filteredItems"
:loading="loading"
:row-key="(row: Item) => row.id"
v-model:checked-row-keys="checkedKeys"
size="medium"
striped
:scroll-x="900"
/>

<!-- AI candidate list -->
<n-modal
v-model:show="suggestVisible"
preset="card"
:title="`${t.threat.aiSuggestion}${itemTypeLabel}`"
style="width: 580px"
>
<div v-if="candidates.length === 0" style="text-align: center; padding: 24px; color: #aaa">
{{ t.threat.noNewSuggestions }}
</div>
<n-list v-else bordered>
<n-list-item v-for="(c, i) in candidates" :key="i">
<n-thing :title="c.code">
<template #description>{{ c.description }}</template>
</n-thing>
<template #suffix>
<n-space>
<template v-if="canWrite">
<n-button
size="small"
type="primary"
:loading="adoptingIndex === i"
@click="adoptCandidate(c, i)"
>{{ t.threat.adopt }}</n-button>
<n-button size="small" @click="candidates.splice(i, 1)">{{ t.threat.ignore }}</n-button>
</template>
</n-space>
</template>
</n-list-item>
</n-list>
<template #footer>
<n-button @click="suggestVisible = false">{{ t.threat.close }}</n-button>
</template>
</n-modal>

<!-- Add / edit drawer -->
<n-drawer v-model:show="drawerVisible" :width="440" placement="right">
<n-drawer-content :title="editItem ? `${t.common.edit} ${editItem.code}` : `${t.threat.newAdd}${itemTypeLabel}`" closable>
<n-form
ref="formRef"
:model="editForm"
label-placement="top"
size="small"
:disabled="!canWrite"
>
<n-form-item :label="t.threat.code" :rule="{ required: true, message: t.threat.code + ' ' + t.common.required }">
<n-input v-model:value="editForm.code" :placeholder="`${codePrefix}001`" />
</n-form-item>
<n-form-item :label="t.common.description">
<n-input v-model:value="editForm.description" type="textarea" :rows="5" />
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
<n-form-item v-if="editItem && sourceObjectiveMap[editItem.id]?.length" :label="t.threat.relatedObjectives">
<n-space size="small" wrap>
<n-button
v-for="objective in sourceObjectiveMap[editItem.id]"
:key="objective.id"
size="tiny"
tertiary
@click="goToObjective(objective.id)"
>
{{ objective.code }}
</n-button>
</n-space>
</n-form-item>
</n-form>

<n-divider />
<n-space justify="end">
<n-button @click="drawerVisible = false">{{ t.common.cancel }}</n-button>
<n-button v-if="canWrite" type="primary" :loading="saveLoading" @click="saveItem">{{ t.common.save }}</n-button>
</n-space>
</n-drawer-content>
</n-drawer>
</div>
</template>

<script setup lang="ts">
import { ref, computed, h, watch, onMounted, type ComputedRef } from 'vue'
import { useMessage, NButton, NTag, NSpace, NTooltip, NIcon } from 'naive-ui'
import { AlertCircleOutline } from '@vicons/ionicons5'
import { useRoute, useRouter } from 'vue-router'
import { threatApi } from '@/api/threats'
import { securityApi } from '@/api/security'
import type { Assumption, OSP } from '@/api/threats'
import type { SecurityObjective, ObjectiveSources } from '@/api/security'
import type { DataTableColumns, DataTableRowKey } from 'naive-ui'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))

type Item = Assumption | OSP

const props = defineProps<{
toeId: string
items: Item[]
objectives: SecurityObjective[]
objectiveSourcesMap: Record<string, ObjectiveSources>
loading: boolean
canWrite: boolean
itemType: 'assumption' | 'osp'
codePrefix: string
}>()
const emit = defineEmits<{ (e: 'refresh'): void }>()
const message = useMessage()
const route = useRoute()
const router = useRouter()
const canWrite = computed(() => props.canWrite)

const itemTypeLabel = computed(() => props.itemType === 'assumption' ? t.value.threat.assumptions : t.value.threat.osp)
const objectiveOptions = computed(() => props.objectives
  .filter(item => props.itemType !== 'assumption' || item.obj_type === 'OE')
  .map(item => ({
  label: `${item.code} (${item.obj_type})`,
  value: item.id,
})))

const sourceObjectiveMap = computed(() => {
  const map: Record<string, SecurityObjective[]> = {}
  for (const objective of props.objectives) {
    const sourceIds = props.itemType === 'assumption'
      ? (props.objectiveSourcesMap[objective.id]?.assumption_ids ?? [])
      : (props.objectiveSourcesMap[objective.id]?.osp_ids ?? [])
    for (const sourceId of sourceIds) {
      if (!map[sourceId]) map[sourceId] = []
      map[sourceId].push(objective)
    }
  }
  return map
})

// ── Multi-select ──
const checkedKeys = ref<DataTableRowKey[]>([])
const batchDeleting = ref(false)
const batchConfirming = ref(false)

async function batchDelete() {
  batchDeleting.value = true
  try {
    for (const id of checkedKeys.value) {
      if (props.itemType === 'assumption') {
        await threatApi.deleteAssumption(props.toeId, id as string)
      } else {
        await threatApi.deleteOsp(props.toeId, id as string)
      }
    }
    checkedKeys.value = []
    message.success(t.value.common.success)
    emit('refresh')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    batchDeleting.value = false
  }
}

async function batchConfirm() {
  if (checkedKeys.value.length === 0) {
    message.warning(t.value.common.selectAtLeast)
    return
  }
  batchConfirming.value = true
  try {
    const ids = checkedKeys.value as string[]
    if (props.itemType === 'assumption') {
      await threatApi.batchConfirmAssumptions(props.toeId, ids)
    } else {
      await threatApi.batchConfirmOsps(props.toeId, ids)
    }
    checkedKeys.value = []
    message.success(t.value.common.success)
    emit('refresh')
  } catch (e: any) {
    message.error(e.message || t.value.common.error)
  } finally {
    batchConfirming.value = false
  }
}

// ── Filter ──
const filterStatus = ref<string | null>(null)
const statusOptions = computed(() => [
{ label: t.value.threat.statusPending, value: 'pending' },
{ label: t.value.threat.statusConfirmed, value: 'confirmed' },
{ label: t.value.threat.statusRejected, value: 'rejected' },
])

const filteredItems = computed(() => {
if (!filterStatus.value) return props.items
return props.items.filter(i => i.review_status === filterStatus.value)
})

function statusTagType(s: string) {
return s === 'confirmed' ? 'success' : s === 'rejected' ? 'error' : 'default'
}
function statusLabel(s: string) {
return s === 'confirmed' ? t.value.threat.statusConfirmed : s === 'rejected' ? t.value.threat.statusRejected : t.value.threat.statusPending
}

// ── Table columns ──
const codeLabel = computed(() => props.itemType === 'assumption' ? t.value.threat.assumptionCode : t.value.threat.ospCode)
type ItemCols = DataTableColumns<Item>
const columns: ComputedRef<ItemCols> = computed(() => [
...(canWrite.value ? [{ type: 'selection' as const, width: 40, fixed: 'left' as const }] : []),
{
  title: codeLabel.value,
  key: 'code',
  width: 160,
},
{
  title: props.itemType === 'assumption' ? t.value.threat.assumptionDefinition : t.value.threat.ospDefinition,
  key: 'description',
  minWidth: 300,
  titleStyle: { whiteSpace: 'nowrap' },
  render: row => {
    const text = row.description?.trim()
    if (!text) return h('span', { style: 'color:#aaa' }, '-')
    return h('span', { style: 'display:block; line-height:1.7; padding:4px 0; word-break:break-word' }, text)
  },
},
{
title: t.value.threat.linkedObjectives,
key: 'linked_objectives',
width: 240,
render: row => {
  const linkedObjectives = sourceObjectiveMap.value[row.id] ?? []
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
  title: t.value.threat.actions,
  key: 'actions',
  width: 140,
  titleStyle: { whiteSpace: 'nowrap' },
  fixed: 'right',
  render: row =>
    h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openEdit(row) }, () => t.value.common.edit),
      ...(canWrite.value ? [
        h(NButton, {
          size: 'tiny',
          text: true,
          type: 'primary',
          disabled: row.review_status === 'confirmed',
          onClick: () => confirmItem(row),
        }, () => t.value.threat.confirmThreat),
        h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => deleteItem(row) }, () => t.value.common.delete),
      ] : []),
    ]),
},
])

// ── Add / Edit drawer ──
const drawerVisible = ref(false)
const editItem = ref<Item | null>(null)
const saveLoading = ref(false)
const editForm = ref({ code: '', description: '', objective_ids: [] as string[] })

function openAdd() {
editItem.value = null
editForm.value = { code: '', description: '', objective_ids: [] }
drawerVisible.value = true
}

function openEdit(item: Item) {
editItem.value = item
editForm.value = {
  code: item.code,
  description: item.description ?? '',
  objective_ids: (sourceObjectiveMap.value[item.id] ?? []).map(objective => objective.id),
}
drawerVisible.value = true
}

function sourceTypeValue() {
  return props.itemType === 'assumption' ? 'assumption' : 'osp'
}

function focusQueryKey() {
  return props.itemType === 'assumption' ? 'focusAssumptionId' : 'focusOspId'
}

function goToObjective(objectiveId: string) {
  router.push({ name: 'Security', query: { toeId: props.toeId, tab: 'objectives', focusObjectiveId: objectiveId } })
}

async function syncSourceObjectives(sourceId: string, nextObjectiveIds: string[]) {
  const currentObjectiveIds = (sourceObjectiveMap.value[sourceId] ?? []).map(objective => objective.id)
  const toAdd = nextObjectiveIds.filter(id => !currentObjectiveIds.includes(id))
  const toRemove = currentObjectiveIds.filter(id => !nextObjectiveIds.includes(id))

  await Promise.all(toAdd.map(objectiveId =>
    securityApi.addSourceMapping(props.toeId, objectiveId, sourceTypeValue(), sourceId)
  ))
  await Promise.all(toRemove.map(objectiveId =>
    securityApi.removeSourceMapping(props.toeId, objectiveId, sourceTypeValue(), sourceId)
  ))
}

function handleFocusedItem() {
  const focusId = typeof route.query[focusQueryKey()] === 'string' ? route.query[focusQueryKey()] : null
  if (!focusId) return
  const item = props.items.find(entry => entry.id === focusId)
  if (!item) return
  openEdit(item)
  router.replace({ query: { ...route.query, [focusQueryKey()]: undefined } })
}

async function saveItem() {
saveLoading.value = true
try {
if (editItem.value) {
if (props.itemType === 'assumption') {
await threatApi.updateAssumption(props.toeId, editItem.value.id, editForm.value)
} else {
await threatApi.updateOsp(props.toeId, editItem.value.id, editForm.value)
}
await syncSourceObjectives(editItem.value.id, editForm.value.objective_ids)
message.success(t.value.common.success)
} else {
let createdId = ''
if (props.itemType === 'assumption') {
const res = await threatApi.createAssumption(props.toeId, editForm.value)
createdId = res.data.id
} else {
const res = await threatApi.createOsp(props.toeId, editForm.value)
createdId = res.data.id
}
await syncSourceObjectives(createdId, editForm.value.objective_ids)
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

async function deleteItem(item: Item) {
try {
if (props.itemType === 'assumption') {
await threatApi.deleteAssumption(props.toeId, item.id)
} else {
await threatApi.deleteOsp(props.toeId, item.id)
}
message.success(t.value.common.success)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function confirmItem(item: Item) {
try {
if (props.itemType === 'assumption') {
await threatApi.confirmAssumption(props.toeId, item.id)
} else {
await threatApi.confirmOsp(props.toeId, item.id)
}
message.success(t.value.threat.statusConfirmed)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function rejectItem(item: Item) {
try {
if (props.itemType === 'assumption') {
await threatApi.rejectAssumption(props.toeId, item.id)
} else {
await threatApi.rejectOsp(props.toeId, item.id)
}
message.success(t.value.threat.statusRejected)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

async function revertItem(item: Item) {
try {
if (props.itemType === 'assumption') {
await threatApi.revertAssumption(props.toeId, item.id)
} else {
await threatApi.revertOsp(props.toeId, item.id)
}
message.success(t.value.threat.statusPending)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

// ── AI suggestion ──
const aiLoading = ref(false)
const suggestVisible = ref(false)
const candidates = ref<any[]>([])
const adoptingIndex = ref<number | null>(null)

async function openAiSuggest() {
aiLoading.value = true
try {
let res: any
if (props.itemType === 'assumption') {
res = await threatApi.aiSuggestAssumptions(props.toeId, localeStore.lang)
} else {
res = await threatApi.aiSuggestOsps(props.toeId, localeStore.lang)
}
candidates.value = res.data ?? []
suggestVisible.value = true
} catch (e: any) {
message.error(e.message)
} finally {
aiLoading.value = false
}
}

async function adoptCandidate(c: any, index: number) {
adoptingIndex.value = index
try {
const payload = { code: c.code, description: c.description }
if (props.itemType === 'assumption') {
await threatApi.createAssumption(props.toeId, payload)
} else {
await threatApi.createOsp(props.toeId, payload)
}
candidates.value.splice(index, 1)
message.success(t.value.threat.adopt)
emit('refresh')
} catch (e: any) {
message.error(e.message)
} finally {
adoptingIndex.value = null
}
}

watch(() => props.items, () => {
  handleFocusedItem()
}, { deep: true })

watch(() => route.query[focusQueryKey()], () => {
  handleFocusedItem()
})

onMounted(() => {
  handleFocusedItem()
})
</script>