<template>
  <div>
    <n-page-header :title="t.risk.title" :subtitle="t.risk.subtitle" />
    <n-empty
      style="margin-top: 80px"
      :description="t.risk.pendingImplementation"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
</script>
