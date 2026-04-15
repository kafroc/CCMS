<template>
  <div>
    <n-page-header :title="t.threat.title" subtitle="">
      <template #extra>
        <n-select
          v-model:value="selectedToeId"
          :options="toeOptions"
          :placeholder="t.threat.selectToe"
          style="width: 260px"
          @update:value="onToeChange"
        />
      </template>
    </n-page-header>

    <div v-if="!selectedToeId" style="margin-top: 80px; text-align: center">
      <n-empty :description="t.threat.selectToeTip" />
    </div>

    <template v-else>
      <n-tabs v-model:value="activeTab" type="line" style="margin-top: 16px">
        <n-tab-pane name="threats">
          <template #tab>
            {{ t.threat.threats }}
            <n-badge v-if="threats.length" :value="threats.length" :max="99" style="margin-left: 6px" />
          </template>
          <ThreatsTab
            :toe-id="selectedToeId"
            :threats="threats"
            :objectives="objectives"
            :objective-sources-map="objectiveSourcesMap"
            :loading="threatsLoading"
            :can-write="currentToeCanWrite"
            @refresh="refreshAll"
          />
        </n-tab-pane>

        <n-tab-pane name="assumptions">
          <template #tab>
            {{ t.threat.assumptions }}
            <n-badge v-if="assumptions.length" :value="assumptions.length" :max="99" style="margin-left: 6px" />
          </template>
          <SPDTab
            :toe-id="selectedToeId"
            :items="assumptions"
            :objectives="objectives"
            :objective-sources-map="objectiveSourcesMap"
            :loading="assumptionsLoading"
            :can-write="currentToeCanWrite"
            item-type="assumption"
            code-prefix="A."
            @refresh="refreshAll"
          />
        </n-tab-pane>

        <n-tab-pane name="osps">
          <template #tab>
            {{ t.threat.osp }}
            <n-badge v-if="osps.length" :value="osps.length" :max="99" style="margin-left: 6px" />
          </template>
          <SPDTab
            :toe-id="selectedToeId"
            :items="osps"
            :objectives="objectives"
            :objective-sources-map="objectiveSourcesMap"
            :loading="ospsLoading"
            :can-write="currentToeCanWrite"
            item-type="osp"
            code-prefix="P."
            @refresh="refreshAll"
          />
        </n-tab-pane>

        <n-tab-pane name="completeness">
          <template #tab>
            {{ t.threat.completenessCheck }}
          </template>
          <CompletenessTab
            :toe-id="selectedToeId"
            :active="activeTab === 'completeness'"
            :refresh-token="refreshToken"
          />
        </n-tab-pane>
      </n-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { toeApi } from '@/api/toes'
import { threatApi } from '@/api/threats'
import { securityApi } from '@/api/security'
import type { Threat, Assumption, OSP } from '@/api/threats'
import type { SecurityObjective, ObjectiveSources } from '@/api/security'
import ThreatsTab from './ThreatsTab.vue'
import SPDTab from './SPDTab.vue'
import CompletenessTab from './CompletenessTab.vue'
import { useLocaleStore } from '@/stores/locale'
import { useToeSelectionStore } from '@/stores/toeSelection'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const toeSelectionStore = useToeSelectionStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const route = useRoute()
const router = useRouter()

const toeList = ref<any[]>([])
const selectedToeId = ref<string | null>(null)
const activeTab = ref('threats')
const refreshToken = ref(0)
const objectives = ref<SecurityObjective[]>([])
const objectiveSourcesMap = ref<Record<string, ObjectiveSources>>({})

const toeOptions = computed(() =>
  toeList.value.map(t => ({ label: t.name, value: t.id }))
)

const currentToe = computed(() => toeList.value.find(item => item.id === selectedToeId.value) ?? null)
const currentToeCanWrite = computed(() => currentToe.value?.access_level !== 'read')

function buildThreatQuery(toeId: string, tab: string) {
  return {
    ...route.query,
    toeId,
    tab,
  }
}

async function loadToes() {
  try {
    const res = await toeApi.list()
    toeList.value = res.data
    const routeToeId = typeof route.query.toeId === 'string' ? route.query.toeId : null
    const storedToeId = toeSelectionStore.selectedToeId
    const initialToeId = routeToeId && res.data.some((item: any) => item.id === routeToeId)
      ? routeToeId
      : storedToeId && res.data.some((item: any) => item.id === storedToeId)
        ? storedToeId
        : res.data[0]?.id
    const routeTab = typeof route.query.tab === 'string' ? route.query.tab : null
    if (routeTab && ['threats', 'assumptions', 'osps', 'completeness'].includes(routeTab)) {
      activeTab.value = routeTab
    }
    if (initialToeId && !selectedToeId.value) {
      selectedToeId.value = initialToeId
      toeSelectionStore.setSelectedToeId(initialToeId)
      onToeChange(initialToeId)
    }
  } catch (e: any) {
    message.error(e.message)
  }
}

function onToeChange(id: string) {
  selectedToeId.value = id
  toeSelectionStore.setSelectedToeId(id)
  router.replace({ name: 'Threats', query: buildThreatQuery(id, activeTab.value) })
  loadThreats()
  loadAssumptions()
  loadOsps()
  loadObjectiveMappings()
}

function refreshAll() {
  loadThreats()
  loadAssumptions()
  loadOsps()
  loadObjectiveMappings()
  refreshToken.value += 1
}

async function loadObjectiveMappings() {
  if (!selectedToeId.value) return
  try {
    const res = await securityApi.listObjectives(selectedToeId.value)
    objectives.value = res.data
    const mappingEntries = await Promise.all(
      res.data.map(async objective => {
        const sourceRes = await securityApi.listObjectiveSources(selectedToeId.value!, objective.id)
        return [objective.id, sourceRes.data] as const
      })
    )
    objectiveSourcesMap.value = Object.fromEntries(mappingEntries)
  } catch (e: any) {
    message.error(e.message)
  }
}

const threats = ref<Threat[]>([])
const threatsLoading = ref(false)
async function loadThreats() {
  if (!selectedToeId.value) return
  threatsLoading.value = true
  try {
    const res = await threatApi.listThreats(selectedToeId.value)
    threats.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    threatsLoading.value = false
  }
}

const assumptions = ref<Assumption[]>([])
const assumptionsLoading = ref(false)
async function loadAssumptions() {
  if (!selectedToeId.value) return
  assumptionsLoading.value = true
  try {
    const res = await threatApi.listAssumptions(selectedToeId.value)
    assumptions.value = res.data
    refreshToken.value += 1
  } catch (e: any) {
    message.error(e.message)
  } finally {
    assumptionsLoading.value = false
  }
}

const osps = ref<OSP[]>([])
const ospsLoading = ref(false)
async function loadOsps() {
  if (!selectedToeId.value) return
  ospsLoading.value = true
  try {
    const res = await threatApi.listOsps(selectedToeId.value)
    osps.value = res.data
    refreshToken.value += 1
  } catch (e: any) {
    message.error(e.message)
  } finally {
    ospsLoading.value = false
  }
}

onMounted(loadToes)

watch(activeTab, value => {
  if (selectedToeId.value) {
    router.replace({ name: 'Threats', query: buildThreatQuery(selectedToeId.value, value) })
  }
})

watch(() => route.query.toeId, value => {
  if (typeof value === 'string' && value !== selectedToeId.value && toeList.value.some(item => item.id === value)) {
    onToeChange(value)
  }
})

watch(() => route.query.tab, value => {
  if (typeof value === 'string' && ['threats', 'assumptions', 'osps', 'completeness'].includes(value) && value !== activeTab.value) {
    activeTab.value = value
  }
})
</script>