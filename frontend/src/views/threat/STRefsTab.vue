<template>
<div>
<!-- Upload area -->
<n-card size="small" style="margin-bottom: 16px">
<n-space align="center">
<n-upload
:custom-request="handleUpload"
:show-file-list="false"
accept=".pdf,.doc,.docx,.html,.htm"
>
<n-button :loading="uploading">{{ t.threat.uploadStDoc }}</n-button>
</n-upload>
<span style="color: #aaa; font-size: 12px">{{ t.threat.supportFormat }}</span>
</n-space>
</n-card>

<!-- List -->
<n-data-table
:columns="columns"
:data="refs"
:loading="loading"
:row-key="(row: STReference) => row.id"
size="small"
/>

<!-- Parsed content viewer modal -->
<n-modal
v-model:show="viewVisible"
preset="card"
:title="t.threat.stParseContent"
style="width: 720px; max-height: 80vh"
>
<n-tabs type="line" v-if="viewRef">
<n-tab-pane name="threats" :tab="t.threat.threats">
<n-code :code="prettyJson(viewRef.threats_extracted)" language="json" />
</n-tab-pane>
<n-tab-pane name="objectives" :tab="t.threat.securityObjectives">
<n-code :code="prettyJson(viewRef.objectives_extracted)" language="json" />
</n-tab-pane>
<n-tab-pane name="sfr" :tab="t.security.sfrs">
<n-code :code="prettyJson(viewRef.sfr_extracted)" language="json" />
</n-tab-pane>
<n-tab-pane name="assets" :tab="t.toe.assets">
<n-code :code="prettyJson(viewRef.assets_extracted)" language="json" />
</n-tab-pane>
</n-tabs>
</n-modal>
</div>
</template>

<script setup lang="ts">
import { ref, h, onUnmounted, onMounted, watch, computed, type ComputedRef, type Ref } from 'vue'
import { useMessage, NButton, NTag, NSpace } from 'naive-ui'
import { threatApi } from '@/api/threats'
import type { STReference } from '@/api/threats'
import type { DataTableColumns, UploadCustomRequestOptions } from 'naive-ui'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))

const props = defineProps<{
toeId: string
refs: STReference[]
loading: boolean
}>()
const emit = defineEmits<{ (e: 'refresh'): void }>()
const message = useMessage()

// ── Upload ──
const uploading = ref(false)

async function handleUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
uploading.value = true
try {
// Use filename (without extension) as product name
const productName = file.name ? file.name.replace(/\.[^.]+$/, '') : 'Untitled'
await threatApi.uploadStRef(props.toeId, productName, file.file as File, localeStore.lang)
message.success(t.value.toe.fileUploadSuccess)
onFinish()
emit('refresh')
// Start polling for newly uploaded items
setTimeout(() => startPolling(), 1500)
} catch (e: any) {
message.error(e.message)
onError()
} finally {
uploading.value = false
}
}

// ── Table columns ──
type STRefCols = DataTableColumns<STReference>
function statusTagType(s: string) {
if (s === 'completed' || s === 'ready') return 'success'
if (s === 'failed') return 'error'
if (s === 'processing') return 'warning'
return 'default'
}
function statusLabel(s: string) {
if (s === 'completed' || s === 'ready') return t.value.threat.parsed
if (s === 'failed') return t.value.threat.parseFailed
if (s === 'processing') return t.value.threat.parsing
return t.value.threat.toBeParsed
}

const columns: ComputedRef<STRefCols> = computed(() => [
{ title: t.value.threat.productName, key: 'product_name', ellipsis: { tooltip: true } },
{
title: t.value.threat.fileType,
key: 'product_type',
width: 90,
render: row => row.product_type
? h(NTag, { size: 'small', type: 'default' }, () => row.product_type)
: h('span', { style: 'color:#aaa' }, '-'),
},
{
title: t.value.threat.parseStatus,
key: 'parse_status',
width: 110,
render: row => {
const isProcessing = row.parse_status === 'processing' || row.parse_status === 'pending'
return h(NSpace, { align: 'center', size: 4 }, () => [
h(NTag, { type: statusTagType(row.parse_status), size: 'small' }, () => statusLabel(row.parse_status)),
...(isProcessing ? [h('span', { style: 'font-size:11px;color:#aaa' }, '...')] : []),
])
},
},
{
title: t.value.toe.operation,
key: 'actions',
width: 160,
render: row => {
const btns: ReturnType<typeof h>[] = []
if (row.parse_status === 'completed' || row.parse_status === 'ready') {
btns.push(h(NButton, { size: 'tiny', onClick: () => openView(row) }, () => t.value.threat.viewContent))
}
if (row.parse_status === 'failed') {
btns.push(h(NButton, { size: 'tiny', type: 'warning', onClick: () => retryParse(row) }, () => t.value.threat.retry))
}
btns.push(
h(NButton, { size: 'tiny', type: 'error', quaternary: true, onClick: () => deleteRef(row) }, () => t.value.common.delete),
)
return h(NSpace, { size: 4 }, () => btns)
},
},
])

// ── View parsing content ──
const viewVisible = ref(false)
const viewRef: Ref<STReference | null> = ref(null)

function openView(r: STReference) {
viewRef.value = r
viewVisible.value = true
}

function prettyJson(val: string | null) {
if (!val) return '(No Data)'
try {
return JSON.stringify(JSON.parse(val), null, 2)
} catch {
return val
}
}

// ── Actions ──
async function retryParse(r: STReference) {
try {
await threatApi.retryStRef(props.toeId, r.id, localeStore.lang)
message.success(t.value.common.success)
emit('refresh')
setTimeout(() => startPolling(), 1500)
} catch (e: any) { message.error(e.message) }
}

async function deleteRef(r: STReference) {
try {
await threatApi.deleteStRef(props.toeId, r.id)
message.success(t.value.common.success)
emit('refresh')
} catch (e: any) { message.error(e.message) }
}

// ── Poll for in-process records ──
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
if (pollTimer) return
pollTimer = setInterval(() => {
const hasProcessing = props.refs.some(r => r.parse_status === 'processing' || r.parse_status === 'pending')
if (hasProcessing) emit('refresh')
else stopPolling()
}, 3000)
}

function stopPolling() {
if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// Kick off polling if items are already processing on mount
onMounted(() => {
const hasProcessing = props.refs.some(r => r.parse_status === 'processing' || r.parse_status === 'pending')
if (hasProcessing) startPolling()
})

watch(() => props.refs, (newRefs) => {
const hasProcessing = newRefs.some(r => r.parse_status === 'processing' || r.parse_status === 'pending')
if (hasProcessing) startPolling()
else stopPolling()
})

onUnmounted(stopPolling)
</script>