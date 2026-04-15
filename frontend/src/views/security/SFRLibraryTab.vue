<template>
  <div>
    <n-space justify="space-between" style="margin-bottom: 12px; flex-wrap: wrap" :size="12">
      <n-space style="flex-wrap: wrap" align="center">
        <n-select
          v-model:value="filterClass"
          :options="classOptions"
          :placeholder="t.security.sfrLibraryFilterClass"
          clearable
          style="width: 220px"
          @update:value="onSearch"
        />
        <n-input
          v-model:value="keyword"
          :placeholder="t.security.sfrLibrarySearch"
          clearable
          style="width: 240px"
          @update:value="onSearch"
        />
      </n-space>
      <n-space :size="8" style="flex-wrap: wrap">
        <n-button v-if="canManage" size="small" @click="openCreate">
          {{ t.security.addSfr }}
        </n-button>
        <n-button
          v-if="canManage && checkedRowKeys.length > 0"
          size="small"
          :loading="batchDeleting"
          @click="handleBatchDelete"
        >
          {{ t.security.deleteSelected }} ({{ checkedRowKeys.length }})
        </n-button>
        <n-button size="small" @click="downloadTemplate">
          {{ t.security.downloadTemplate }}
        </n-button>
        <n-button size="small" @click="exportCsv">
          {{ t.security.exportCsv }}
        </n-button>
        <n-button v-if="canManage" size="small" :loading="importing" @click="importModalVisible = true">
          {{ t.security.importSfrLibrary }}
        </n-button>
      </n-space>
    </n-space>

    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row: SFRLibraryItem) => row.id"
      v-model:checked-row-keys="checkedRowKeys"
      size="small"
      :pagination="false"
    />

    <n-drawer v-model:show="drawerVisible" :width="620" placement="right">
      <n-drawer-content :title="drawerTitle" closable>
        <n-form :model="editForm" label-placement="top" size="small" :disabled="!canManage">
          <n-form-item :label="t.security.sfrId" required>
            <n-input v-model:value="editForm.sfr_component" />
          </n-form-item>
          <n-form-item :label="t.security.sfrName">
            <n-input v-model:value="editForm.sfr_component_name" />
          </n-form-item>
          <n-form-item :label="t.security.sfrDetail">
            <n-input
              v-model:value="editForm.description"
              class="sfr-library-detail-textarea"
              type="textarea"
              :autosize="{ minRows: 6, maxRows: 18 }"
            />
          </n-form-item>
          <n-form-item :label="t.security.dependencies">
            <n-input v-model:value="editForm.dependencies" type="textarea" :rows="3" />
          </n-form-item>
        </n-form>
        <n-divider />
        <n-space justify="end">
          <n-button v-if="canManage && editItem" :loading="deleting" @click="handleDeleteSingle">{{ t.common.delete }}</n-button>
          <n-button @click="drawerVisible = false">{{ t.common.cancel }}</n-button>
          <n-button v-if="canManage" :loading="saving" @click="handleSave">{{ t.common.save }}</n-button>
        </n-space>
      </n-drawer-content>
    </n-drawer>

    <n-modal v-model:show="importModalVisible" preset="card" :title="t.security.uploadSfrDocument" style="width: 520px">
      <n-space vertical :size="16">
        <div style="color: #666">{{ t.security.uploadSfrDocumentHint }}</div>
        <n-upload
          :custom-request="handleImportUpload"
          :show-file-list="false"
          accept=".csv,text/csv"
        >
          <n-button :loading="importing">{{ t.security.importSfrLibrary }}</n-button>
        </n-upload>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="closeImportModal">{{ t.common.cancel }}</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="importErrorModalVisible" preset="card" :title="t.security.importErrorRowsTitle" style="width: 760px">
      <n-space vertical :size="12">
        <div style="color: #666">{{ t.security.importErrorRowsHint }}</div>
        <n-data-table
          :columns="importErrorColumns"
          :data="importErrors"
          size="small"
          :pagination="false"
          :max-height="420"
        />
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="importErrorModalVisible = false">{{ t.common.cancel }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, computed, onMounted, type ComputedRef } from 'vue'
import { useMessage, NButton } from 'naive-ui'
import { securityApi, type SFRLibraryItem } from '@/api/security'
import type { DataTableColumns, DataTableRowKey, UploadCustomRequestOptions } from 'naive-ui'
import { useLocaleStore } from '@/stores/locale'
import { useAuthStore } from '@/stores/auth'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const authStore = useAuthStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const emit = defineEmits<{ (e: 'stats', total: number): void }>()
const canManage = computed(() => authStore.isAdmin)

const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const batchDeleting = ref(false)
const importing = ref(false)
const items = ref<SFRLibraryItem[]>([])
const importErrors = ref<Array<{ row: number; sfr_id?: string | null; reason: string }>>([])
const importErrorModalVisible = ref(false)
const total = ref(0)
const classOptions = ref<any[]>([])
const filterClass = ref<string | null>(null)
const keyword = ref('')
const checkedRowKeys = ref<DataTableRowKey[]>([])
const pageSize = 10000

const drawerTitle = computed(() => (editItem.value ? t.value.security.editSfr : t.value.security.addSfr))

function wrapCell(value: string | null | undefined) {
  return h('div', {
    style: {
      whiteSpace: 'normal',
      wordBreak: 'break-word',
      overflowWrap: 'anywhere',
      lineHeight: '1.5',
      padding: '6px 0',
    },
  }, value || '-')
}

type LibraryColumns = DataTableColumns<SFRLibraryItem>
const columns: ComputedRef<LibraryColumns> = computed(() => [
  ...(canManage.value ? [{ type: 'selection' as const, width: 36, minWidth: 28, resizable: true }] : []),
  { title: t.value.security.sfrId, key: 'sfr_component', width: 112, minWidth: 72, resizable: true, render: row => wrapCell(row.sfr_component) },
  { title: t.value.security.sfrName, key: 'sfr_component_name', width: 220, minWidth: 150, resizable: true, render: row => wrapCell(row.sfr_component_name) },
  { title: t.value.security.sfrDetail, key: 'description', width: 500, minWidth: 280, resizable: true, render: row => wrapCell(row.description) },
  { title: t.value.security.dependencies, key: 'dependencies', width: 220, minWidth: 150, resizable: true, render: row => wrapCell(row.dependencies) },
  ...(canManage.value ? [{
    title: t.value.toe.operation,
    key: 'actions',
    width: 120,
    minWidth: 110,
    resizable: true,
    render: (row: SFRLibraryItem) => h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, () => t.value.common.edit),
  }] : []),
])

const importErrorColumns = computed<DataTableColumns<{ row: number; sfr_id?: string | null; reason: string }>>(() => [
  { title: t.value.security.importRowNumber, key: 'row', width: 90 },
  { title: t.value.security.sfrId, key: 'sfr_id', width: 160, render: row => row.sfr_id || '-' },
  { title: t.value.security.importErrorReason, key: 'reason', render: row => wrapCell(row.reason) },
])

async function loadData(page = 1) {
  loading.value = true
  try {
    const params: any = { page, page_size: pageSize }
    if (filterClass.value) params.sfr_class = filterClass.value
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    const res = await securityApi.listSFRLibrary(params)
    items.value = res.data.items
    total.value = res.data.total
    emit('stats', res.data.total)
    if (res.data.classes.length > 0) {
      classOptions.value = res.data.classes
    }
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadData(1), 400)
}

const drawerVisible = ref(false)
const importModalVisible = ref(false)
const editItem = ref<SFRLibraryItem | null>(null)
const editForm = ref({
  sfr_component: '',
  sfr_component_name: '',
  description: '',
  dependencies: '',
})

function openEdit(item: SFRLibraryItem) {
  editItem.value = item
  editForm.value = {
    sfr_component: item.sfr_component,
    sfr_component_name: item.sfr_component_name,
    description: item.description ?? '',
    dependencies: item.dependencies ?? '',
  }
  drawerVisible.value = true
}

function openCreate() {
  editItem.value = null
  editForm.value = {
    sfr_component: '',
    sfr_component_name: '',
    description: '',
    dependencies: '',
  }
  drawerVisible.value = true
}

async function handleSave() {
  if (!editForm.value.sfr_component.trim()) {
    message.warning(t.value.security.sfrIdRequired)
    return
  }
  saving.value = true
  try {
    const payload = {
      sfr_component: editForm.value.sfr_component,
      sfr_component_name: editForm.value.sfr_component_name,
      description: editForm.value.description,
      dependencies: editForm.value.dependencies,
    }
    if (editItem.value) {
      await securityApi.updateSFRLibrary(editItem.value.id, payload)
    } else {
      await securityApi.createSFRLibrary(payload)
    }
    message.success(t.value.common.success)
    drawerVisible.value = false
    editItem.value = null
    await loadData()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

async function handleDeleteSingle() {
  if (!editItem.value) return
  deleting.value = true
  try {
    const deletingId = editItem.value.id
    await securityApi.deleteSFRLibrary(deletingId)
    message.success(t.value.common.success)
    drawerVisible.value = false
    editItem.value = null
    checkedRowKeys.value = checkedRowKeys.value.filter(id => id !== deletingId)
    await loadData()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    deleting.value = false
  }
}

async function handleBatchDelete() {
  if (!checkedRowKeys.value.length) return
  batchDeleting.value = true
  try {
    await securityApi.batchDeleteSFRLibrary(checkedRowKeys.value as string[])
    message.success(t.value.common.success)
    checkedRowKeys.value = []
    await loadData()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    batchDeleting.value = false
  }
}

async function handleImportUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  importing.value = true
  try {
    const res = await securityApi.importSFRLibraryFromDoc(file.file as File)
    const parts: string[] = []
    if (res.data.imported) parts.push(t.value.security.importedCount.replace('{count}', String(res.data.imported)))
    if (res.data.updated) parts.push(t.value.security.updatedCount.replace('{count}', String(res.data.updated)))
    message.success(parts.join(' / ') || t.value.common.success)
    importModalVisible.value = false
    checkedRowKeys.value = []
    importErrors.value = res.data.errors ?? []
    importErrorModalVisible.value = importErrors.value.length > 0
    await loadData()
    onFinish()
  } catch (e: any) {
    message.error(e.message)
    onError()
  } finally {
    importing.value = false
  }
}

function downloadTemplate() {
  const content = [
    'SFR ID,SFR Name,SFR Detail,Dependencies',
    'FDP_ACC.1,Subset access control,"The TSF shall enforce the [assignment: access control SFP] on [assignment: subjects, objects, and operations among subjects and objects covered by the SFP].","FIA_UID.1, FIA_UAU.1"',
  ].join('\r\n')
  const blob = new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'sfr-library-template.csv'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  message.success(t.value.security.templateDownloaded)
}

function escapeCsvCell(value: string | null | undefined) {
  const normalized = String(value ?? '').replace(/\r?\n/g, '\n')
  return `"${normalized.replace(/"/g, '""')}"`
}

function exportCsv() {
  if (!items.value.length) {
    message.warning(t.value.common.noData)
    return
  }

  const header = ['SFR ID', 'SFR Name', 'SFR Detail', 'Dependencies']
  const rows = items.value.map(item => [
    item.sfr_component,
    item.sfr_component_name,
    item.description,
    item.dependencies,
  ])

  const content = [
    header.join(','),
    ...rows.map(row => row.map(cell => escapeCsvCell(cell)).join(',')),
  ].join('\r\n')

  const timestamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
  const blob = new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sfr-library-export-${timestamp}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  message.success(t.value.security.sfrLibraryExported.replace('{count}', String(items.value.length)))
}

function closeImportModal() {
  importModalVisible.value = false
}

onMounted(() => loadData(1))
</script>

<style scoped>
.sfr-library-detail-textarea :deep(textarea) {
  resize: none;
}
</style>
