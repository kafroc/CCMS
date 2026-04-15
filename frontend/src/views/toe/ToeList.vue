<template>
  <div>
    <n-page-header :title="t.toe.title" :subtitle="t.toe.toeDescription">
      <template #extra>
        <n-space align="center" wrap>
          <n-input
            v-model:value="searchText"
            :placeholder="t.common.search"
            clearable
            style="width: 200px"
            @update:value="loadToes"
          />
          <n-select
            v-model:value="filterType"
            :placeholder="t.toe.toeType"
            clearable
            style="width: 140px"
            :options="typeOptions"
            @update:value="loadToes"
          />
          <n-button class="toolbar-btn" :disabled="toes.length === 0" @click="showExportModal = true">
            {{ t.toe.exportToe }}
          </n-button>
          <n-button class="toolbar-btn" :loading="importing" @click="triggerImport">
            {{ t.toe.importToe }}
          </n-button>
          <n-button class="toolbar-btn" @click="router.push('/toes/create')">
            <template #icon><n-icon><AddOutline /></n-icon></template>
            {{ t.toe.createToe }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-spin :show="loading" style="margin-top: 16px; min-height: 200px">
      <div v-if="toes.length > 0" class="toe-grid">
        <div v-for="toe in toes" :key="toe.id" class="toe-grid-item">
          <n-card
            hoverable
            class="toe-card"
            @click="router.push(`/toes/${toe.id}`)"
          >
            <template #header>
              <n-ellipsis :line-clamp="1" style="max-width: 100%">{{ toe.name }}</n-ellipsis>
            </template>
            <template #header-extra>
              <n-tag :type="typeTagMap[toe.toe_type] || 'default'" size="small">
                {{ typeLabel[toe.toe_type] || toe.toe_type }}
              </n-tag>
            </template>

            <div class="toe-card-body">
              <n-text depth="3" class="toe-card-intro">
                {{ toe.brief_intro || '—' }}
              </n-text>
              <div class="toe-card-meta">
                <n-text depth="3" style="font-size: 12px">
                  {{ t.toe.assets }}: {{ toe.asset_count ?? 0 }}
                </n-text>
                <n-text depth="3" style="font-size: 12px">
                  {{ t.toe.files }}: {{ toe.file_count ?? 0 }}
                </n-text>
                <n-text v-if="toe.version" depth="3" style="font-size: 12px">
                  {{ toe.version }}
                </n-text>
              </div>
            </div>

            <template #action>
              <n-space justify="end">
                <n-button v-if="toe.access_level !== 'read'" size="small" type="error" ghost @click.stop="handleDelete(toe)">
                  {{ t.common.delete }}
                </n-button>
              </n-space>
            </template>
          </n-card>
        </div>
      </div>
      <n-empty
        v-if="!loading && toes.length === 0"
        :description="t.toe.noToes"
        style="margin-top: 80px"
      />
    </n-spin>

    <!-- Delete confirmation dialog -->
    <n-modal v-model:show="showDeleteModal" preset="dialog" :title="t.common.confirmDelete" type="warning">
      <template v-if="deletingToe">
        <n-alert type="warning" style="margin-bottom: 16px">
          {{ t.common.confirmDelete }} TOE "{{ deletingToe.name }}"?
        </n-alert>
        <n-spin :show="loadingCounts">
          <n-descriptions bordered :column="2" size="small" v-if="cascadeCounts">
            <n-descriptions-item :label="t.toe.assets">{{ cascadeCounts.asset_count }}</n-descriptions-item>
            <n-descriptions-item :label="t.toe.files">{{ cascadeCounts.file_count }}</n-descriptions-item>
            <n-descriptions-item :label="t.threat.threats">{{ cascadeCounts.threat_count }}</n-descriptions-item>
            <n-descriptions-item :label="t.threat.assumptions + '/' + t.threat.osp">{{ (cascadeCounts.assumption_count || 0) + (cascadeCounts.osp_count || 0) }}</n-descriptions-item>
            <n-descriptions-item :label="t.security.securityObjectives">{{ cascadeCounts.objective_count }}</n-descriptions-item>
            <n-descriptions-item :label="t.security.sfrs">{{ cascadeCounts.sfr_count }}</n-descriptions-item>
            <n-descriptions-item :label="t.test.title">{{ cascadeCounts.test_count }}</n-descriptions-item>
            <n-descriptions-item :label="t.risk.title">{{ cascadeCounts.risk_count }}</n-descriptions-item>
          </n-descriptions>
        </n-spin>
        <n-form-item :label="t.toe.toeName" style="margin-top: 16px">
          <n-input v-model:value="deleteConfirmName" :placeholder="deletingToe.name" />
        </n-form-item>
      </template>
      <template #action>
        <n-space>
          <n-button @click="showDeleteModal = false">{{ t.common.cancel }}</n-button>
          <n-button
            type="error"
            :disabled="deleteConfirmName !== deletingToe?.name"
            :loading="deleting"
            @click="confirmDelete"
          >
            {{ t.common.confirm }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="showExportModal" preset="dialog" :title="t.toe.exportToe">
      <n-form-item :label="t.toe.selectExportToe">
        <n-select
          v-model:value="selectedExportToeId"
          :placeholder="t.toe.selectExportToe"
          :options="exportToeOptions"
        />
      </n-form-item>
      <template #action>
        <n-space>
          <n-button @click="showExportModal = false">{{ t.common.cancel }}</n-button>
          <n-button class="toolbar-btn" :loading="exporting" :disabled="!selectedExportToeId" @click="confirmExport">
            {{ t.toe.exportToe }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <input ref="importInputRef" type="file" accept=".toe,application/zip" style="display: none" @change="handleImportFileChange" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { toeApi, type TOE, type CascadeCounts } from '@/api/toes'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
const router = useRouter()
const message = useMessage()

const toes = ref<TOE[]>([])
const loading = ref(false)
const searchText = ref('')
const filterType = ref<string | null>(null)

const typeOptions = computed(() => [
  { label: t.value.toe.hardware, value: 'hardware' },
  { label: t.value.toe.software, value: 'software' },
  { label: t.value.toe.system, value: 'system' },
])

const typeLabel = computed(() => ({
  hardware: t.value.toe.hardware,
  software: t.value.toe.software,
  system: t.value.toe.system,
} as Record<string, string>))

const typeTagMap: Record<string, string> = { hardware: 'info', software: 'success', system: 'warning' }

const showDeleteModal = ref(false)
const deletingToe = ref<TOE | null>(null)
const cascadeCounts = ref<CascadeCounts | null>(null)
const loadingCounts = ref(false)
const deleteConfirmName = ref('')
const deleting = ref(false)
const showExportModal = ref(false)
const selectedExportToeId = ref<string | null>(null)
const exporting = ref(false)
const importing = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)

const exportToeOptions = computed(() => toes.value.map((toe) => ({ label: toe.name, value: toe.id })))

async function loadToes() {
  loading.value = true
  try {
    const params: any = {}
    if (searchText.value) params.search = searchText.value
    if (filterType.value) params.toe_type = filterType.value
    const res = await toeApi.list(params)
    toes.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function sanitizeExportFileName(name: string) {
  return (name || 'toe-export').replace(/[\\/:*?"<>|]+/g, '_').trim() || 'toe-export'
}

async function confirmExport() {
  if (!selectedExportToeId.value) return
  const toe = toes.value.find((item) => item.id === selectedExportToeId.value)
  if (!toe) return

  exporting.value = true
  try {
    const blob = await toeApi.exportPackage(toe.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${sanitizeExportFileName(toe.name)}.toe`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    showExportModal.value = false
    message.success(t.value.toe.exportToeSuccess.replace('{name}', toe.name))
  } catch (e: any) {
    message.error(e.message)
  } finally {
    exporting.value = false
  }
}

function triggerImport() {
  if (importing.value) return
  importInputRef.value?.click()
}

async function handleImportFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return

  importing.value = true
  try {
    const res = await toeApi.importPackage(file)
    message.success(t.value.toe.importToeSuccess.replace('{name}', res.data.name))
    selectedExportToeId.value = res.data.id
    await loadToes()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    importing.value = false
  }
}

async function handleDelete(toe: TOE) {
  deletingToe.value = toe
  deleteConfirmName.value = ''
  cascadeCounts.value = null
  showDeleteModal.value = true
  loadingCounts.value = true
  try {
    const res = await toeApi.getCascadeCounts(toe.id)
    cascadeCounts.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loadingCounts.value = false
  }
}

async function confirmDelete() {
  if (!deletingToe.value) return
  deleting.value = true
  try {
    await toeApi.delete(deletingToe.value.id)
    message.success(t.value.common.success)
    showDeleteModal.value = false
    loadToes()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    deleting.value = false
  }
}

onMounted(loadToes)
</script>

<style scoped>
.toolbar-btn {
  --n-color: #ffffff !important;
  --n-color-hover: #f3f4f6 !important;
  --n-color-pressed: #e5e7eb !important;
  --n-text-color: #111111 !important;
  --n-text-color-hover: #111111 !important;
  --n-text-color-pressed: #111111 !important;
  --n-border: 1px solid #111111 !important;
  --n-border-hover: 1px solid #111111 !important;
  --n-border-pressed: 1px solid #111111 !important;
  --n-ripple-color: rgba(17, 17, 17, 0.08) !important;
}

.toe-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 16px;
  align-items: stretch;
}

@media (max-width: 1100px) {
  .toe-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 700px) {
  .toe-grid {
    grid-template-columns: 1fr;
  }
}

.toe-grid-item {
  display: flex;
  flex-direction: column;
}

.toe-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.toe-card :deep(.n-card__content) {
  flex: 1;
}

.toe-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.toe-card-intro {
  font-size: 13px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}

.toe-card-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: auto;
}
</style>
