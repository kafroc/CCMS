<template>
  <div class="settings-page">
    <h2 class="page-title">{{ t.settings.title }}</h2>

    <n-tabs type="line" animated>
      <!-- Language tab -->
      <n-tab-pane name="language" :tab="t.settings.language">
        <div class="tab-content lang-tab">
          <p class="desc">{{ t.settings.languageDesc }}</p>
          <div class="lang-list">
            <div
              v-for="item in langOptions"
              :key="item.code"
              class="lang-item"
              :class="{ active: localeStore.lang === item.code }"
              @click="selectLang(item.code)"
            >
              <span class="lang-flag">{{ item.flag }}</span>
              <span class="lang-name">{{ item.label }}</span>
              <n-icon v-if="localeStore.lang === item.code" class="check-icon" :size="18">
                <CheckmarkCircleOutline />
              </n-icon>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <!-- AI model management tab -->
      <n-tab-pane name="ai-models" :tab="t.settings.aiModels">
        <div class="tab-content">
          <AIModelList />
        </div>
      </n-tab-pane>

      <!-- User management tab (admin only) -->
      <n-tab-pane v-if="authStore.isAdmin" name="users" :tab="t.settings.userManage">
        <div class="tab-content">
          <UserList />
        </div>
      </n-tab-pane>

      <!-- System settings tab (admin only) -->
      <n-tab-pane v-if="authStore.isAdmin" name="system" :tab="t.settings.systemSettings">
        <div class="tab-content" style="max-width: 520px">
          <n-spin :show="systemLoading">
            <n-form label-placement="top">
              <n-form-item :label="t.settings.pdfParseTimeout">
                <template #label>
                  <div>
                    <div style="font-weight: 500">{{ t.settings.pdfParseTimeout }}</div>
                    <div style="font-size: 12px; color: #888; margin-top: 2px">{{ t.settings.pdfParseTimeoutDesc }}</div>
                  </div>
                </template>
                <n-input-number
                  v-model:value="pdfTimeout"
                  :min="30"
                  :max="3600"
                  style="width: 200px"
                />
              </n-form-item>
              <n-space>
                <n-button type="primary" :loading="systemSaving" @click="saveSystemSettings">
                  {{ t.common.save }}
                </n-button>
              </n-space>
            </n-form>
          </n-spin>
        </div>
      </n-tab-pane>

      <!-- Log tab (admin only) -->
      <n-tab-pane v-if="authStore.isAdmin" name="logs" :tab="t.settings.logs">
        <div class="tab-content">
          <LogsTab />
        </div>
      </n-tab-pane>

      <!-- ST Template tab -->
      <n-tab-pane name="st-template" :tab="t.settings.stTemplate">
        <div class="tab-content">
          <div style="margin-bottom: 12px">
            <p class="desc">{{ t.settings.stTemplateDesc }}</p>
            <n-space style="margin-top: 8px">
              <n-button :style="btnStyle" :loading="stTemplateSaving" @click="saveSTTemplate">
                {{ t.settings.stTemplateSaveToFile }}
              </n-button>
              <n-button :style="btnStyle" :loading="stTemplateLoading" @click="loadSTTemplate">
                {{ t.settings.stTemplateLoadFromFile }}
              </n-button>
            </n-space>
          </div>
          <div class="st-template-hint" style="margin-bottom: 12px">
            <n-collapse :default-expanded-names="[]">
              <n-collapse-item :title="t.settings.stTemplatePlaceholders" name="placeholders">
                <div class="placeholder-groups">
                  <div v-for="group in stPlaceholderGroups" :key="group.title" class="placeholder-group">
                    <div class="placeholder-group-title">{{ group.title }}</div>
                    <div class="placeholder-list">
                      <code v-for="item in group.items" :key="item" class="placeholder-token">{{ item }}</code>
                    </div>
                  </div>
                </div>
              </n-collapse-item>
            </n-collapse>
          </div>
          <n-spin :show="stTemplateLoading">
            <n-input
              v-model:value="stTemplateContent"
              type="textarea"
              :rows="30"
              :placeholder="t.settings.stTemplatePlaceholder"
              style="font-family: 'Consolas', 'Monaco', monospace; font-size: 13px"
            />
          </n-spin>
        </div>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { NIcon, useMessage } from 'naive-ui'
import { CheckmarkCircleOutline } from '@vicons/ionicons5'
import { useLocaleStore, type LangCode } from '@/stores/locale'
import { useAuthStore } from '@/stores/auth'
import { getMessages, getLangNames } from '@/locales'
import { systemApi } from '@/api/system'
import { exportApi } from '@/api/export'
import AIModelList from '@/views/aimodel/AIModelList.vue'
import UserList from '@/views/user/UserList.vue'
import LogsTab from '@/views/settings/LogsTab.vue'

const localeStore = useLocaleStore()
const authStore = useAuthStore()
const message = useMessage()

const t = computed(() => getMessages(localeStore.lang))
const btnStyle = { backgroundColor: '#fff', color: '#000', border: '1px solid #d9d9d9' }

// ── System settings ──
const systemLoading = ref(false)
const systemSaving = ref(false)
const pdfTimeout = ref(300)

async function loadSystemSettings() {
  if (!authStore.isAdmin) return
  systemLoading.value = true
  try {
    const res = await systemApi.getSettings()
    const v = res.data?.pdf_parse_timeout_seconds?.value
    if (v !== undefined) pdfTimeout.value = parseInt(v)
  } catch {
    // ignore
  } finally {
    systemLoading.value = false
  }
}

async function saveSystemSettings() {
  systemSaving.value = true
  try {
    await systemApi.updateSettings({ pdf_parse_timeout_seconds: pdfTimeout.value })
    message.success(t.value.settings.settingsSaved)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    systemSaving.value = false
  }
}

onMounted(() => {
  loadSystemSettings()
  loadSTTemplate()
})

// ── ST Template ──
const stTemplateContent = ref('')
const stTemplateLoading = ref(false)
const stTemplateSaving = ref(false)
const stPlaceholderGroups = [
  {
    title: computed(() => t.value.settings.placeholderToe).value,
    items: ['{TOE Name}', '{TOE Version}', '{TOE Type}', '{TOE Brief Intro}', '{TOE Type Desc}', '{TOE Usage}', '{Major Security Features}', '{Required Non-TOE}', '{Physical Scope}', '{Logical Scope}', '{HW Interfaces}', '{SW Interfaces}'],
  },
  {
    title: computed(() => t.value.settings.placeholderAssets).value,
    items: ['{Assets Table}'],
  },
  {
    title: computed(() => t.value.settings.placeholderThreats).value,
    items: ['{Threats Table}', '{Threat Objective rationale}', '{Threat Objective Mapping}'],
  },
  {
    title: computed(() => t.value.settings.placeholderAssumptions).value,
    items: ['{Assumptions Table}', '{Assumption Objective rationale}', '{Assumption Objective Mapping}'],
  },
  {
    title: computed(() => t.value.settings.placeholderOsp).value,
    items: ['{OSP Table}', '{OSP Objective rationale}', '{OSP Objective Mapping}'],
  },
  {
    title: computed(() => t.value.settings.placeholderObjectives).value,
    items: ['{Objectives Table}', '{OE Table}', '{TAO Objective Mapping}', '{Objective SFR Mapping}', '{Objective SFR rationale}'],
  },
  {
    title: computed(() => t.value.settings.placeholderSfr).value,
    items: ['{SFR Table}', '{SFR Dependencies}'],
  },
  {
    title: computed(() => t.value.settings.placeholderTests).value,
    items: ['{Test Cases Table}'],
  },
]

async function loadSTTemplate() {
  stTemplateLoading.value = true
  try {
    const res = await exportApi.getSTTemplate()
    stTemplateContent.value = res.data?.content ?? ''
  } catch {
    // ignore
  } finally {
    stTemplateLoading.value = false
  }
}

async function saveSTTemplate() {
  stTemplateSaving.value = true
  try {
    await exportApi.updateSTTemplate(stTemplateContent.value)
    message.success(t.value.settings.settingsSaved)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    stTemplateSaving.value = false
  }
}

const langFlags: Record<string, string> = {
  zh: '🇨🇳',
  'zh-TW': '🇭🇰',
  en: '🇺🇸',
  ko: '🇰🇷',
  ja: '🇯🇵',
  de: '🇩🇪',
  es: '🇪🇸',
  fr: '🇫🇷',
  pt: '🇧🇷',
}

const langNames = getLangNames()
const langOptions: { code: LangCode; flag: string; label: string }[] = Object.entries(langNames).map(([code, label]) => ({
  code: code as LangCode,
  flag: langFlags[code] || '🌐',
  label,
}))

function selectLang(code: LangCode) {
  localeStore.setLang(code)
  const msg = getMessages(code)
  message.success(msg.settings.saved)
}
</script>

<style scoped>
.settings-page {
  max-width: 100%;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1B4F8A;
  margin: 0 0 20px 0;
}

.tab-content {
  padding: 16px 0;
}

.lang-tab {
  max-width: 600px;
}

.desc {
  color: #666;
  font-size: 13px;
  margin: 0 0 20px 0;
}

.placeholder-groups {
  display: grid;
  gap: 12px;
}

.placeholder-group {
  padding: 10px 12px;
  border: 1px solid #ececec;
  border-radius: 8px;
  background: #fafafa;
}

.placeholder-group-title {
  font-size: 12px;
  font-weight: 600;
  color: #444;
  margin-bottom: 8px;
}

.placeholder-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.placeholder-token {
  display: inline-block;
  padding: 4px 8px;
  font-size: 12px;
  color: #555;
  background: #fff;
  border: 1px solid #e3e3e3;
  border-radius: 6px;
}

.lang-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lang-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1.5px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s;
  background: #fff;
}

.lang-item:hover {
  border-color: #1B4F8A;
  background: #f0f5ff;
}

.lang-item.active {
  border-color: #1B4F8A;
  background: #e8f0fd;
}

.lang-flag {
  font-size: 22px;
  line-height: 1;
  width: 28px;
  text-align: center;
}

.lang-name {
  font-size: 15px;
  flex: 1;
  color: #222;
}

.check-icon {
  color: #1B4F8A;
}
</style>
