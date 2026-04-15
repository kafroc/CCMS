<template>
  <div class="logs-tab">
    <n-tabs v-model:value="activeTab" type="line" animated size="small">
      <!-- Audit log -->
      <n-tab-pane name="audit" :tab="labels.audit">
        <div class="filters">
          <n-input
            v-model:value="auditFilters.username"
            :placeholder="labels.filterUsername"
            clearable
            size="small"
            style="width: 160px"
          />
          <n-select
            v-model:value="auditFilters.method"
            :options="methodOptions"
            :placeholder="labels.filterMethod"
            clearable
            size="small"
            style="width: 120px"
          />
          <n-input
            v-model:value="auditFilters.resource"
            :placeholder="labels.filterResource"
            clearable
            size="small"
            style="width: 140px"
          />
          <n-select
            v-model:value="auditStatusFilter"
            :options="statusOptions"
            :placeholder="labels.filterStatus"
            clearable
            size="small"
            style="width: 160px"
          />
          <n-button size="small" type="primary" @click="loadAudit(1)">{{ labels.apply }}</n-button>
          <n-button size="small" @click="resetAuditFilters">{{ labels.reset }}</n-button>
          <n-button size="small" secondary @click="refreshAudit">{{ labels.refresh }}</n-button>
          <n-popconfirm @positive-click="clearAudit">
            <template #trigger>
              <n-button size="small" type="warning" secondary>{{ labels.clearOld }}</n-button>
            </template>
            {{ labels.confirmClear }}
          </n-popconfirm>
        </div>

        <n-data-table
          :columns="auditColumns"
          :data="auditData.items"
          :loading="auditLoading"
          :bordered="false"
          size="small"
          :row-key="(r: any) => r.id"
          style="margin-top: 12px"
        />

        <div class="pagination">
          <n-pagination
            v-model:page="auditData.page"
            :page-count="Math.max(1, Math.ceil(auditData.total / auditData.page_size))"
            :page-size="auditData.page_size"
            @update:page="loadAudit"
          />
          <span class="total">{{ labels.total }}: {{ auditData.total }}</span>
        </div>
      </n-tab-pane>

      <!-- Error log -->
      <n-tab-pane name="errors" :tab="labels.errors">
        <div class="filters">
          <n-input
            v-model:value="errorFilters.error_type"
            :placeholder="labels.filterErrorType"
            clearable
            size="small"
            style="width: 200px"
          />
          <n-select
            v-model:value="errorFilters.level"
            :options="levelOptions"
            :placeholder="labels.filterLevel"
            clearable
            size="small"
            style="width: 140px"
          />
          <n-button size="small" type="primary" @click="loadErrors(1)">{{ labels.apply }}</n-button>
          <n-button size="small" @click="resetErrorFilters">{{ labels.reset }}</n-button>
          <n-button size="small" secondary @click="refreshErrors">{{ labels.refresh }}</n-button>
          <n-popconfirm @positive-click="clearErrors">
            <template #trigger>
              <n-button size="small" type="warning" secondary>{{ labels.clearOld }}</n-button>
            </template>
            {{ labels.confirmClear }}
          </n-popconfirm>
        </div>

        <n-data-table
          :columns="errorColumns"
          :data="errorData.items"
          :loading="errorLoading"
          :bordered="false"
          size="small"
          :row-key="(r: any) => r.id"
          style="margin-top: 12px"
        />

        <div class="pagination">
          <n-pagination
            v-model:page="errorData.page"
            :page-count="Math.max(1, Math.ceil(errorData.total / errorData.page_size))"
            :page-size="errorData.page_size"
            @update:page="loadErrors"
          />
          <span class="total">{{ labels.total }}: {{ errorData.total }}</span>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- Error detail drawer -->
    <n-drawer v-model:show="detailShow" :width="720" placement="right">
      <n-drawer-content :title="labels.errorDetail" closable>
        <template v-if="detailRow">
          <n-descriptions label-placement="left" :column="1" bordered size="small">
            <n-descriptions-item :label="labels.col.time">{{ formatTime(detailRow.created_at) }}</n-descriptions-item>
            <n-descriptions-item :label="labels.col.errorType">{{ detailRow.error_type }}</n-descriptions-item>
            <n-descriptions-item :label="labels.col.level">{{ detailRow.level }}</n-descriptions-item>
            <n-descriptions-item :label="labels.col.user">{{ detailRow.username || '-' }}</n-descriptions-item>
            <n-descriptions-item :label="labels.col.path">{{ detailRow.method || '' }} {{ detailRow.path || '-' }}</n-descriptions-item>
            <n-descriptions-item :label="labels.col.ip">{{ detailRow.ip || '-' }}</n-descriptions-item>
            <n-descriptions-item :label="labels.col.message">
              <pre class="trace">{{ detailRow.message }}</pre>
            </n-descriptions-item>
            <n-descriptions-item :label="labels.col.stack">
              <pre class="trace">{{ detailRow.stack_trace || '-' }}</pre>
            </n-descriptions-item>
          </n-descriptions>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import {
  NButton,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NDrawer,
  NDrawerContent,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NTabs,
  NTabPane,
  NTag,
  useMessage,
} from 'naive-ui'
import { systemApi, type AuditLogItem, type ErrorLogItem } from '@/api/system'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const message = useMessage()
const t = computed(() => getMessages(localeStore.lang))

const labels = computed(() => ({
  audit: t.value.settings.logAudit ?? 'Audit Log',
  errors: t.value.settings.logErrors ?? 'Error Log',
  filterUsername: t.value.settings.logFilterUsername ?? 'Username',
  filterMethod: t.value.settings.logFilterMethod ?? 'Method',
  filterResource: t.value.settings.logFilterResource ?? 'Resource',
  filterStatus: t.value.settings.logFilterStatus ?? 'Status',
  filterErrorType: t.value.settings.logFilterErrorType ?? 'Error Type',
  filterLevel: t.value.settings.logFilterLevel ?? 'Level',
  apply: t.value.common?.search ?? 'Apply',
  reset: t.value.common?.reset ?? 'Reset',
  refresh: t.value.common?.refresh ?? 'Refresh',
  clearOld: t.value.settings.logClearOld ?? 'Clear 30-day+',
  confirmClear: t.value.settings.logConfirmClear ?? 'Delete log entries older than 30 days?',
  total: t.value.common?.total ?? 'Total',
  errorDetail: t.value.settings.logErrorDetail ?? 'Error Detail',
  col: {
    time: t.value.settings.logColTime ?? 'Time',
    user: t.value.settings.logColUser ?? 'User',
    method: t.value.settings.logColMethod ?? 'Method',
    path: t.value.settings.logColPath ?? 'Path',
    status: t.value.settings.logColStatus ?? 'Status',
    ip: t.value.settings.logColIp ?? 'IP',
    duration: t.value.settings.logColDuration ?? 'Duration',
    errorType: t.value.settings.logColErrorType ?? 'Error',
    level: t.value.settings.logColLevel ?? 'Level',
    message: t.value.settings.logColMessage ?? 'Message',
    stack: t.value.settings.logColStack ?? 'Stack trace',
  },
}))

const activeTab = ref<'audit' | 'errors'>('audit')

// ── Audit log ───────────────────────────────────────
const auditLoading = ref(false)
const auditData = reactive({
  items: [] as AuditLogItem[],
  total: 0,
  page: 1,
  page_size: 50,
})
const auditFilters = reactive({
  username: '',
  method: null as string | null,
  resource: '',
})
const auditStatusFilter = ref<string | null>(null)

const methodOptions = [
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
]
const statusOptions = [
  { label: '2xx', value: '200-299' },
  { label: '3xx', value: '300-399' },
  { label: '4xx', value: '400-499' },
  { label: '5xx', value: '500-599' },
]
const levelOptions = [
  { label: 'ERROR', value: 'ERROR' },
  { label: 'WARNING', value: 'WARNING' },
  { label: 'CRITICAL', value: 'CRITICAL' },
]

function formatTime(iso?: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function statusTagType(code: number): 'success' | 'info' | 'warning' | 'error' | 'default' {
  if (code >= 500) return 'error'
  if (code >= 400) return 'warning'
  if (code >= 300) return 'info'
  if (code >= 200) return 'success'
  return 'default'
}

const auditColumns = computed(() => [
  { title: labels.value.col.time, key: 'created_at', width: 170, render: (r: AuditLogItem) => formatTime(r.created_at) },
  { title: labels.value.col.user, key: 'username', width: 120, render: (r: AuditLogItem) => r.username || '-' },
  { title: labels.value.col.method, key: 'method', width: 80 },
  { title: labels.value.col.path, key: 'path', ellipsis: { tooltip: true } },
  {
    title: labels.value.col.status,
    key: 'status_code',
    width: 80,
    render: (r: AuditLogItem) =>
      h(NTag, { type: statusTagType(r.status_code), size: 'small', round: true }, { default: () => String(r.status_code) }),
  },
  { title: labels.value.col.ip, key: 'ip', width: 140, render: (r: AuditLogItem) => r.ip || '-' },
  {
    title: labels.value.col.duration,
    key: 'duration_ms',
    width: 100,
    render: (r: AuditLogItem) => (r.duration_ms != null ? `${r.duration_ms} ms` : '-'),
  },
])

async function loadAudit(page = auditData.page) {
  auditLoading.value = true
  try {
    const params: any = {
      page,
      page_size: auditData.page_size,
    }
    if (auditFilters.username) params.username = auditFilters.username
    if (auditFilters.method) params.method = auditFilters.method
    if (auditFilters.resource) params.resource = auditFilters.resource
    if (auditStatusFilter.value) {
      const [lo, hi] = auditStatusFilter.value.split('-').map(Number)
      params.status_min = lo
      params.status_max = hi
    }
    const res = await systemApi.getAuditLogs(params)
    auditData.items = res.data.items
    auditData.total = res.data.total
    auditData.page = res.data.page
    auditData.page_size = res.data.page_size
  } catch (e: any) {
    message.error(e.message || 'Failed to load audit logs')
  } finally {
    auditLoading.value = false
  }
}
const refreshAudit = () => loadAudit(auditData.page)
function resetAuditFilters() {
  auditFilters.username = ''
  auditFilters.method = null
  auditFilters.resource = ''
  auditStatusFilter.value = null
  loadAudit(1)
}
async function clearAudit() {
  try {
    const res = await systemApi.clearAuditLogs(30)
    message.success(`Deleted ${res.data.deleted}`)
    loadAudit(1)
  } catch (e: any) {
    message.error(e.message)
  }
}

// ── Error log ───────────────────────────────────────
const errorLoading = ref(false)
const errorData = reactive({
  items: [] as ErrorLogItem[],
  total: 0,
  page: 1,
  page_size: 50,
})
const errorFilters = reactive({
  level: null as string | null,
  error_type: '',
})

const detailShow = ref(false)
const detailRow = ref<ErrorLogItem | null>(null)

function openDetail(r: ErrorLogItem) {
  detailRow.value = r
  detailShow.value = true
}

const errorColumns = computed(() => [
  { title: labels.value.col.time, key: 'created_at', width: 170, render: (r: ErrorLogItem) => formatTime(r.created_at) },
  {
    title: labels.value.col.level,
    key: 'level',
    width: 90,
    render: (r: ErrorLogItem) =>
      h(NTag, { type: r.level === 'CRITICAL' ? 'error' : r.level === 'WARNING' ? 'warning' : 'error', size: 'small' }, { default: () => r.level }),
  },
  { title: labels.value.col.errorType, key: 'error_type', width: 180, ellipsis: { tooltip: true } },
  { title: labels.value.col.message, key: 'message', ellipsis: { tooltip: true } },
  { title: labels.value.col.user, key: 'username', width: 120, render: (r: ErrorLogItem) => r.username || '-' },
  { title: labels.value.col.path, key: 'path', width: 220, ellipsis: { tooltip: true } },
  {
    title: '',
    key: 'actions',
    width: 80,
    render: (r: ErrorLogItem) =>
      h(
        NButton,
        { size: 'tiny', text: true, type: 'primary', onClick: () => openDetail(r) },
        { default: () => labels.value.errorDetail },
      ),
  },
])

async function loadErrors(page = errorData.page) {
  errorLoading.value = true
  try {
    const params: any = { page, page_size: errorData.page_size }
    if (errorFilters.level) params.level = errorFilters.level
    if (errorFilters.error_type) params.error_type = errorFilters.error_type
    const res = await systemApi.getErrorLogs(params)
    errorData.items = res.data.items
    errorData.total = res.data.total
    errorData.page = res.data.page
    errorData.page_size = res.data.page_size
  } catch (e: any) {
    message.error(e.message || 'Failed to load error logs')
  } finally {
    errorLoading.value = false
  }
}
const refreshErrors = () => loadErrors(errorData.page)
function resetErrorFilters() {
  errorFilters.level = null
  errorFilters.error_type = ''
  loadErrors(1)
}
async function clearErrors() {
  try {
    const res = await systemApi.clearErrorLogs(30)
    message.success(`Deleted ${res.data.deleted}`)
    loadErrors(1)
  } catch (e: any) {
    message.error(e.message)
  }
}

onMounted(() => {
  loadAudit(1)
  loadErrors(1)
})
</script>

<style scoped>
.logs-tab {
  padding: 4px 0;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.pagination {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 16px;
}
.total {
  font-size: 12px;
  color: #888;
}
.trace {
  margin: 0;
  padding: 8px 10px;
  background: #f5f5f5;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow: auto;
}
</style>
