<template>
  <div class="export-st-page">
    <n-page-header :title="t.exportSt.title">
      <template #extra>
        <n-space align="center">
          <n-select
            v-model:value="selectedToeId"
            :options="toeOptions"
            :placeholder="t.exportSt.selectToe"
            style="width: 260px"
            @update:value="onToeChange"
          />
          <n-button
            v-if="userEdited"
            :style="{ backgroundColor: '#d03050', color: '#fff', border: 'none' }"
            :loading="refreshing"
            @click="refreshContent"
          >{{ t.exportSt.update }}</n-button>
          <n-dropdown :options="exportOptions" @select="onExport">
            <n-button :style="btnStyle" :loading="exporting">
              {{ t.exportSt.exportSt }}
            </n-button>
          </n-dropdown>
        </n-space>
      </template>
    </n-page-header>

    <div v-if="!selectedToeId" style="margin-top: 80px; text-align: center">
      <n-empty :description="t.exportSt.selectToeFirst" />
    </div>

    <template v-else>
      <n-spin :show="loading" style="min-height: 300px; margin-top: 16px">
        <div class="st-content-shell">
          <div class="st-toolbar">
            <n-space align="center" justify="space-between">
              <n-space>
                <n-button :style="activeMode === 'preview' ? activeModeStyle : btnStyle" @click="activeMode = 'preview'">
                  {{ t.exportSt.preview }}
                </n-button>
                <n-button :style="activeMode === 'edit' ? activeModeStyle : btnStyle" @click="activeMode = 'edit'">
                  {{ t.exportSt.editMarkdown }}
                </n-button>
              </n-space>
              <span v-if="userEdited" class="edited-hint">{{ t.exportSt.editedHint }}</span>
            </n-space>
          </div>

          <div v-if="activeMode === 'preview'" class="st-preview markdown-body" v-html="renderedHtml"></div>

          <div v-else class="st-editor-wrap">
            <n-input
              v-model:value="stContent"
              type="textarea"
              :autosize="{ minRows: 30 }"
              class="st-editor-input"
              @update:value="onUserEdit"
            />
          </div>
        </div>
      </n-spin>
    </template>
  </div>
</template>

<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { ref, computed, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { toeApi } from '@/api/toes'
import { exportApi } from '@/api/export'
import { useLocaleStore } from '@/stores/locale'
import { useToeSelectionStore } from '@/stores/toeSelection'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const toeSelectionStore = useToeSelectionStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const route = useRoute()
const router = useRouter()

const btnStyle = { backgroundColor: '#fff', color: '#000', border: '1px solid #d9d9d9' }
const activeModeStyle = { backgroundColor: '#111', color: '#fff', border: '1px solid #111' }
const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
})
const defaultTableOpen = md.renderer.rules.table_open
const defaultTableClose = md.renderer.rules.table_close
md.renderer.rules.table_open = (...args) => `<div class="table-wrap">${defaultTableOpen ? defaultTableOpen(...args) : '<table>'}`
md.renderer.rules.table_close = (...args) => `${defaultTableClose ? defaultTableClose(...args) : '</table>'}</div>`

// TOE selection
const toeList = ref<any[]>([])
const selectedToeId = ref<string | null>(null)
const toeOptions = computed(() => toeList.value.map(item => ({ label: item.name, value: item.id })))

// State
const stContent = ref('')
const loading = ref(false)
const refreshing = ref(false)
const exporting = ref(false)
const userEdited = ref(false)
const activeMode = ref<'preview' | 'edit'>('preview')
const renderedHtml = computed(() => md.render(stContent.value || ''))

const exportOptions = computed(() => [
  { label: 'Markdown (.md)', key: 'md' },
  { label: 'Word (.docx)', key: 'docx' },
])

function onUserEdit() {
  userEdited.value = true
}

async function loadToes() {
  const res = await toeApi.list()
  toeList.value = res.data
  const routeToeId = typeof route.query.toeId === 'string' ? route.query.toeId : null
  const storedToeId = toeSelectionStore.selectedToeId
  const initialToeId = routeToeId && res.data.some((item: any) => item.id === routeToeId)
    ? routeToeId
    : storedToeId && res.data.some((item: any) => item.id === storedToeId)
      ? storedToeId
      : res.data[0]?.id
  if (initialToeId) {
    selectedToeId.value = initialToeId
    toeSelectionStore.setSelectedToeId(initialToeId)
    loadPreview()
  }
}

function onToeChange(id: string) {
  selectedToeId.value = id
  toeSelectionStore.setSelectedToeId(id)
  router.replace({ name: 'Export', query: { toeId: id } })
  userEdited.value = false
  loadPreview()
}

async function loadPreview() {
  if (!selectedToeId.value) return
  loading.value = true
  try {
    const res = await exportApi.getSTPreview(selectedToeId.value)
    stContent.value = res.data?.content ?? ''
    userEdited.value = false
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function refreshContent() {
  refreshing.value = true
  try {
    const res = await exportApi.getSTPreview(selectedToeId.value!)
    stContent.value = res.data?.content ?? ''
    userEdited.value = false
    message.success(t.value.common.success)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    refreshing.value = false
  }
}

async function onExport(format: string) {
  if (!selectedToeId.value) return
  exporting.value = true
  try {
    const res = await exportApi.exportST(selectedToeId.value, format as 'md' | 'docx', stContent.value)
    // Handle blob download
    const blob = new Blob([(res as any).data ?? res], { type: (res as any).headers?.['content-type'] || 'application/octet-stream' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ext = format === 'docx' ? 'docx' : 'md'
    const toeName = toeList.value.find(item => item.id === selectedToeId.value)?.name || 'ST'
    a.download = `ST_${toeName.replace(/\s/g, '_')}.${ext}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    message.success(t.value.exportSt.exportSuccess)
  } catch (e: any) {
    message.error(e.message || t.value.common.error)
  } finally {
    exporting.value = false
  }
}

onMounted(loadToes)

watch(() => route.query.toeId, value => {
  if (typeof value === 'string' && value !== selectedToeId.value && toeList.value.some(item => item.id === value)) {
    onToeChange(value)
  }
})
</script>

<style scoped>
.export-st-page {
  max-width: 1200px;
}

.st-content-shell {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  overflow: hidden;
}

.st-toolbar {
  padding: 12px 16px;
  border-bottom: 1px solid #efefef;
  background: linear-gradient(180deg, #fafafa 0%, #f5f5f5 100%);
}

.edited-hint {
  font-size: 12px;
  color: #d03050;
}

.st-preview {
  min-height: 720px;
  padding: 28px 32px;
  background: #fff;
}

.st-editor-wrap {
  padding: 16px;
}

:deep(.st-editor-input textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.7;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  color: #172b4d;
  line-height: 1.35;
  margin-top: 1.6em;
  margin-bottom: 0.7em;
}

.markdown-body :deep(h1) {
  font-size: 32px;
  border-bottom: 1px solid #ececec;
  padding-bottom: 0.4em;
  margin-top: 0;
}

.markdown-body :deep(h2) {
  font-size: 24px;
}

.markdown-body :deep(h3) {
  font-size: 18px;
}

.markdown-body :deep(p),
.markdown-body :deep(li) {
  color: #313131;
  line-height: 1.8;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 22px;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  border-radius: 4px;
  background: #f3f4f6;
  font-size: 0.92em;
}

.markdown-body :deep(pre) {
  padding: 14px 16px;
  border-radius: 8px;
  background: #111827;
  overflow: auto;
}

.markdown-body :deep(pre code) {
  padding: 0;
  color: #f9fafb;
  background: transparent;
}

.markdown-body :deep(table) {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 14px;
}

.markdown-body :deep(.table-wrap) {
  max-width: 100%;
  overflow-x: auto;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
  word-break: break-word;
}

.markdown-body :deep(th) {
  background: #f8fafc;
  color: #1f2937;
  font-weight: 600;
}

.markdown-body :deep(blockquote) {
  margin: 16px 0;
  padding: 8px 16px;
  border-left: 4px solid #d1d5db;
  color: #4b5563;
  background: #f9fafb;
}
</style>