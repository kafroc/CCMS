<template>
  <n-config-provider :theme="theme" :locale="currentLocale" :date-locale="currentDateLocale">
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <router-view />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { darkTheme, zhCN, dateZhCN, enUS, dateEnUS } from 'naive-ui'
import { computed, watch } from 'vue'
import { useLocaleStore } from '@/stores/locale'

const localeStore = useLocaleStore()

// Temporarily fixed to light theme, theme switching can be added later
const theme = computed(() => null)

const currentLocale = computed(() => localeStore.lang === 'en' ? enUS : zhCN)
const currentDateLocale = computed(() => localeStore.lang === 'en' ? dateEnUS : dateZhCN)

watch(
  () => localeStore.lang,
  (newLang) => {
    const title = 'CC Security Management System'
    document.title = title
  }
)

// Set initial title
const initialTitle = 'CC Security Management System'
document.title = initialTitle
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body, #app {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  color: #333;
  background: #f5f6fa;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: #f1f1f1;
}
::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>
