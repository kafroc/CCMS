<template>
  <div>
    <n-page-header :title="t.aiModel.title" :subtitle="t.aiModel.timeoutDesc">
      <template #extra>
        <n-button type="primary" @click="openDrawer()">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          {{ t.aiModel.addModel }}
        </n-button>
      </template>
    </n-page-header>

    <n-card style="margin-top: 16px">
      <n-data-table
        :columns="columns"
        :data="models"
        :loading="loading"
        :row-key="(row: AIModel) => row.id"
        :row-class-name="(row: AIModel) => row.is_active ? 'active-row' : ''"
      />
      <n-empty v-if="!loading && models.length === 0" :description="t.aiModel.noModels" style="margin: 40px 0" />
    </n-card>

    <!-- Add/edit drawer -->
    <n-drawer v-model:show="showDrawer" :width="480" placement="right">
      <n-drawer-content :title="editingId ? t.aiModel.editModel : t.aiModel.addModel" closable>
        <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
          <n-form-item :label="t.aiModel.configName" path="name">
            <n-input v-model:value="form.name" :placeholder="t.aiModel.configName" />
          </n-form-item>
          <n-form-item :label="t.aiModel.apiBaseUrl" path="api_base">
            <n-input v-model:value="form.api_base" :placeholder="t.aiModel.apiBaseUrl" />
          </n-form-item>
          <n-form-item :label="t.aiModel.apiKey" path="api_key">
            <n-input
              v-model:value="form.api_key"
              type="password"
              show-password-on="click"
              :placeholder="editingId ? t.aiModel.leaveBlankToKeep : t.aiModel.apiKey"
            />
          </n-form-item>
          <n-form-item :label="t.aiModel.modelName" path="model_name">
            <n-input v-model:value="form.model_name" :placeholder="t.aiModel.modelName" />
          </n-form-item>
          <n-form-item :label="t.aiModel.timeout" path="timeout_seconds">
            <n-input-number
              v-model:value="form.timeout_seconds"
              :min="10"
              :max="300"
              style="width: 100%"
            />
            <template #feedback>
              <n-text depth="3" style="font-size: 12px">
                {{ t.aiModel.timeoutDesc }}
              </n-text>
            </template>
          </n-form-item>
        </n-form>

        <template #footer>
          <n-space justify="end">
            <n-button @click="showDrawer = false">{{ t.common.cancel }}</n-button>
            <n-button type="primary" :loading="submitting" @click="handleSave">
              {{ editingId ? t.common.update : t.common.create }}
            </n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>

    <!-- Chat window -->
    <n-modal
      v-model:show="showChat"
      preset="card"
      :title="`${t.aiModel.chat}: ${chatModel?.name}`"
      style="width: 680px"
      :mask-closable="true"
      :closable="true"
      @close="showChat = false"
    >
      <div class="chat-window" ref="chatWindowRef">
        <div v-for="(msg, i) in chatMessages" :key="i" :class="['chat-msg', msg.role]">
          <div class="chat-bubble">
            <span v-if="msg.role === 'user'">{{ msg.content }}</span>
            <span v-else v-html="renderMd(msg.content)" />
          </div>
        </div>
        <div v-if="chatLoading" class="chat-msg assistant">
          <div class="chat-bubble loading-bubble">
            <n-spin size="small" />
            <span style="margin-left: 8px; color: #999">{{ t.aiModel.thinking }}</span>
          </div>
        </div>
        <div v-if="chatMessages.length === 0 && !chatLoading" style="text-align: center; padding: 40px 0">
          <n-text depth="3">{{ t.aiModel.startChat }}</n-text>
        </div>
      </div>
      <div class="chat-input-area">
        <n-input
          v-model:value="chatInput"
          type="textarea"
          :rows="3"
          :placeholder="t.aiModel.inputPlaceholder"
          :disabled="chatLoading"
          @keydown.ctrl.enter.prevent="sendChat"
        />
        <n-space justify="end" style="margin-top: 8px">
          <n-button size="small" @click="chatModel && (chatHistories[chatModel.id] = [])">{{ t.aiModel.clearChat }}</n-button>
          <n-button type="primary" size="small" :loading="chatLoading" @click="sendChat">{{ t.aiModel.send }}</n-button>
        </n-space>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, nextTick, type ComputedRef } from 'vue'
import {
  NButton, NSpace, NTag, NIcon, NText, NSpin,
  useMessage, useDialog,
  type FormInst, type FormRules, type DataTableColumns,
} from 'naive-ui'
import { AddOutline, ChatbubblesOutline } from '@vicons/ionicons5'
import { aiModelApi, type AIModel, type ChatMessage } from '@/api/aiModels'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const dialog = useDialog()

const models = ref<AIModel[]>([])
const loading = ref(false)
const showDrawer = ref(false)
const submitting = ref(false)
const editingId = ref<string | null>(null)
const verifyingId = ref<string | null>(null)
const activatingId = ref<string | null>(null)

const formRef = ref<FormInst | null>(null)
const form = ref({ name: '', api_base: '', api_key: '', model_name: '', timeout_seconds: 60 })

// Dialog
const showChat = ref(false)
const chatModel = ref<AIModel | null>(null)
const chatHistories = ref<Record<string, ChatMessage[]>>({})
const chatLoadings = ref<Record<string, boolean>>({})
const chatInput = ref('')
const chatWindowRef = ref<HTMLElement | null>(null)

const chatMessages: ComputedRef<ChatMessage[]> = computed({
  get: () => chatModel.value ? (chatHistories.value[chatModel.value.id] ?? []) : [],
  set: (val) => { if (chatModel.value) chatHistories.value[chatModel.value.id] = val },
})

const chatLoading = computed(() => chatModel.value ? !!chatLoadings.value[chatModel.value.id] : false)

const rules: ComputedRef<FormRules> = computed(() => ({
  name: [{ required: true, message: t.value.aiModel.configName, trigger: 'blur' }],
  api_base: [{ required: true, message: t.value.aiModel.apiBaseUrl, trigger: 'blur' }],
  model_name: [{ required: true, message: t.value.aiModel.modelName, trigger: 'blur' }],
}))

type AIModelCols = DataTableColumns<AIModel>
const columns: ComputedRef<AIModelCols> = computed(() => [
  {
    title: t.value.common.name,
    key: 'name',
    width: 160,
    render: (row) => h(NSpace, { align: 'center', size: 6 }, {
      default: () => [
        row.is_active
          ? h(NTag, { type: 'success', size: 'small', round: true }, { default: () => t.value.aiModel.inUse })
          : null,
        h(NText, {}, { default: () => row.name }),
      ].filter(Boolean),
    }),
  },
  { title: t.value.aiModel.apiBaseUrl, key: 'api_base', ellipsis: { tooltip: true } },
  { title: t.value.aiModel.modelName, key: 'model_name', width: 200, ellipsis: { tooltip: true } },
  {
    title: t.value.aiModel.timeout,
    key: 'timeout_seconds',
    width: 70,
    render: (row) => h(NText, { depth: 3 }, { default: () => `${row.timeout_seconds}s` }),
  },
  {
    title: t.value.aiModel.verify,
    key: 'is_verified',
    width: 90,
    render: (row) =>
      row.is_verified
        ? h(NTag, { type: 'success', size: 'small' }, { default: () => t.value.aiModel.verified })
        : h(NTag, { type: 'default', size: 'small' }, { default: () => t.value.aiModel.notVerified }),
  },
  {
    title: t.value.common.actions,
    key: 'actions',
    width: 280,
    render: (row) => h(NSpace, { size: 4 }, {
      default: () => [
        h(NButton, {
          size: 'small',
          type: 'success',
          ghost: true,
          disabled: row.is_active,
          loading: activatingId.value === row.id,
          onClick: () => handleSetActive(row),
        }, { default: () => row.is_active ? t.value.aiModel.inUse : t.value.aiModel.setAsWorking }),
        h(NButton, {
          size: 'small',
          ghost: true,
          onClick: () => openChat(row),
        }, {
          default: () => t.value.aiModel.chat,
          icon: () => h(NIcon, null, { default: () => h(ChatbubblesOutline) }),
        }),
        h(NButton, {
          size: 'small',
          type: 'primary',
          ghost: true,
          loading: verifyingId.value === row.id,
          onClick: () => handleVerify(row),
        }, { default: () => t.value.aiModel.verify }),
        h(NButton, { size: 'small', onClick: () => openDrawer(row) }, { default: () => t.value.common.edit }),
        h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => handleDelete(row) }, { default: () => t.value.common.delete }),
      ],
    }),
  },
])

async function loadModels() {
  loading.value = true
  try {
    const res = await aiModelApi.list()
    models.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function openDrawer(model?: AIModel) {
  editingId.value = model?.id || null
  form.value = {
    name: model?.name || '',
    api_base: model?.api_base || '',
    api_key: '',
    model_name: model?.model_name || '',
    timeout_seconds: model?.timeout_seconds ?? 60,
  }
  showDrawer.value = true
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  submitting.value = true
  try {
    if (editingId.value) {
      const payload: any = { ...form.value }
      if (!payload.api_key) delete payload.api_key
      await aiModelApi.update(editingId.value, payload)
      message.success(t.value.common.success)
    } else {
      await aiModelApi.create(form.value)
      message.success(t.value.common.success)
    }
    showDrawer.value = false
    loadModels()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function handleVerify(model: AIModel) {
  verifyingId.value = model.id
  try {
    const res = await aiModelApi.verify(model.id)
    if (res.data.is_verified) {
      message.success(t.value.aiModel.verifySuccess)
    } else {
      message.warning(t.value.aiModel.verifyFailed)
    }
    loadModels()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    verifyingId.value = null
  }
}

async function handleSetActive(model: AIModel) {
  activatingId.value = model.id
  try {
    const res = await aiModelApi.setActive(model.id)
    message.success(res.msg || t.value.common.success)
    loadModels()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    activatingId.value = null
  }
}

function handleDelete(model: AIModel) {
  dialog.warning({
    title: t.value.common.confirmDelete,
    content: `${t.value.common.delete} "${model.name}"?`,
    positiveText: t.value.common.confirm,
    negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      try {
        await aiModelApi.delete(model.id)
        message.success(t.value.common.success)
        loadModels()
      } catch (e: any) {
        message.error(e.message)
      }
    },
  })
}

function openChat(model: AIModel) {
  chatModel.value = model
  showChat.value = true
}

async function sendChat() {
  const text = chatInput.value.trim()
  if (!text || chatLoading.value || !chatModel.value) return

  const modelId = chatModel.value.id
  if (!chatHistories.value[modelId]) chatHistories.value[modelId] = []
  const history = chatHistories.value[modelId]

  history.push({ role: 'user', content: text })
  chatInput.value = ''
  chatLoadings.value[modelId] = true
  scrollToBottom()

  try {
    const res = await aiModelApi.chat(modelId, history)
    history.push({ role: 'assistant', content: res.data.content })
    if (history.length > 20) history.splice(0, history.length - 20)
  } catch (e: any) {
    history.push({ role: 'assistant', content: `⚠️ ${e.message}` })
  } finally {
    chatLoadings.value[modelId] = false
    scrollToBottom()
  }
}

function renderMd(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br/>')
}

async function scrollToBottom() {
  await nextTick()
  if (chatWindowRef.value) {
    chatWindowRef.value.scrollTop = chatWindowRef.value.scrollHeight
  }
}

onMounted(loadModels)
</script>

<style scoped>
.chat-window {
  height: 420px;
  overflow-y: auto;
  padding: 16px 12px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chat-msg {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.chat-msg.user {
  justify-content: flex-end;
}

.chat-msg.assistant {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 14px;
  line-height: 1.7;
  font-size: 14px;
  word-break: break-word;
}

.chat-msg.user .chat-bubble {
  background: #2E75B6;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.chat-msg.assistant .chat-bubble {
  background: #f4f6f8;
  color: #222;
  border-bottom-left-radius: 4px;
}

.chat-msg.assistant .chat-bubble :deep(strong) {
  font-weight: 600;
  color: #1a1a1a;
}

.chat-msg.assistant .chat-bubble :deep(em) {
  font-style: italic;
  color: #555;
}

.chat-msg.assistant .chat-bubble :deep(code) {
  background: #e8eaed;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 13px;
}

.loading-bubble {
  background: transparent !important;
  border: none !important;
  padding: 6px 0 !important;
  display: flex;
  align-items: center;
}

.chat-input-area {
  margin-top: 12px;
}

:global(.active-row td) {
  background: #f0faf0 !important;
}
</style>