<template>
  <n-layout has-sider style="height: 100vh">
    <!-- Left navigation -->
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="56"
      :width="220"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <!-- Logo -->
      <div class="logo" :class="{ collapsed }">
        <span class="logo-icon">🛡</span>
        <span v-if="!collapsed" class="logo-text">{{ t.login.title }}</span>
      </div>

      <!-- Navigation menu -->
      <n-menu
        :collapsed="collapsed"
        :collapsed-width="56"
        :collapsed-icon-size="20"
        :options="menuOptions"
        :value="activeKey"
        @update:value="handleMenuClick"
      />

      <!-- User info at the bottom -->
      <div class="sider-footer" :class="{ collapsed }">
        <n-dropdown :options="userMenuOptions" @select="handleUserMenu" trigger="click">
          <div class="user-info">
            <n-avatar round size="small" :style="{ background: '#1B4F8A' }">
              {{ userInitial }}
            </n-avatar>
            <span v-if="!collapsed" class="username">{{ authStore.user?.username }}</span>
          </div>
        </n-dropdown>
      </div>
    </n-layout-sider>

    <!-- Main content on the right -->
    <n-layout>
      <n-layout-content style="height: 100%; overflow: auto; padding: 20px">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NIcon, useMessage } from 'naive-ui'
import {
  HomeOutline,
  ShieldOutline,
  AlertCircleOutline,
  CheckmarkCircleOutline,
  FlaskOutline,
  BarChartOutline,
  DocumentTextOutline,
  PeopleOutline,
  HardwareChipOutline,
  SettingsOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const localeStore = useLocaleStore()
const message = useMessage()
const collapsed = ref(false)

const t = computed(() => getMessages(localeStore.lang))

const userInitial = computed(() =>
  (authStore.user?.username || 'U').charAt(0).toUpperCase()
)

const activeKey = computed(() => route.name as string)

function icon(component: any) {
  return () => h(NIcon, null, { default: () => h(component) })
}

const menuOptions = computed(() => {
  const nav = t.value.nav
  const items = [
    { label: nav.riskDashboard, key: 'Risk', icon: icon(HomeOutline) },
    { label: nav.toeManage, key: 'TOE', icon: icon(HardwareChipOutline) },
    { label: nav.threatManage, key: 'Threats', icon: icon(AlertCircleOutline) },
    { label: nav.securityManage, key: 'Security', icon: icon(ShieldOutline) },
    { label: nav.testManage, key: 'Tests', icon: icon(FlaskOutline) },
    { label: nav.exportST, key: 'Export', icon: icon(DocumentTextOutline) },
    { label: nav.settings, key: 'Settings', icon: icon(SettingsOutline) },
  ]
  return items
})

function handleMenuClick(key: string) {
  router.push({ name: key })
}

const userMenuOptions = computed(() => [
  { label: t.value.common.logout, key: 'logout' },
])

function handleUserMenu(key: string) {
  if (key === 'logout') {
    authStore.logout()
    router.push('/login')
    message.success(t.value.common.logout)
  }
}
</script>

<style scoped>
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 18px;
  border-bottom: 1px solid #f0f0f0;
  cursor: default;
  user-select: none;
}
.logo.collapsed {
  padding: 16px;
  justify-content: center;
}
.logo-icon {
  font-size: 20px;
  flex-shrink: 0;
}
.logo-text {
  font-size: 14px;
  font-weight: 600;
  color: #1B4F8A;
  white-space: normal;
  line-height: 1.25;
  max-width: 138px;
  overflow-wrap: anywhere;
}
.sider-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
}
.sider-footer.collapsed {
  padding: 12px;
  display: flex;
  justify-content: center;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: background 0.2s;
}
.user-info:hover {
  background: #f5f5f5;
}
.username {
  font-size: 13px;
  color: #555;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
