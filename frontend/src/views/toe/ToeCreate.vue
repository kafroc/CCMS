<template>
<div>
<n-page-header :title="t.toe.createToe" @back="router.push('/toes')" />

<n-card style="margin-top: 16px; max-width: 860px">
<n-steps :current="currentStep" style="margin-bottom: 32px">
<n-step :title="t.toe.basicInfo" :description="t.toe.basicInfoDesc" />
<n-step :title="t.toe.confirmEdit" :description="t.toe.confirmEditDesc" />
</n-steps>

<!-- Step 1: Basic Info -->
<div v-if="currentStep === 1">
<n-form ref="step1Ref" :model="form" :rules="step1Rules" label-placement="top">
  <n-form-item :label="t.toe.toeName" path="name">
    <n-input v-model:value="form.name" :placeholder="t.toe.toeName" />
  </n-form-item>
  <n-form-item :label="t.toe.toeType" path="toe_type">
    <n-radio-group v-model:value="form.toe_type">
      <n-space>
        <n-radio value="hardware">{{ t.toe.hardware }}</n-radio>
        <n-radio value="software">{{ t.toe.software }}</n-radio>
        <n-radio value="system">{{ t.toe.system }}</n-radio>
      </n-space>
    </n-radio-group>
  </n-form-item>
  <n-form-item :label="t.toe.briefIntro" path="brief_intro">
    <n-input
      v-model:value="form.brief_intro"
      type="textarea"
      autosize
      :placeholder="t.toe.briefIntroRequired"
      :maxlength="1000"
      show-count
    />
  </n-form-item>
  <n-form-item :label="t.toe.version">
    <n-input v-model:value="form.version" :placeholder="t.toe.version" />
  </n-form-item>
</n-form>
<n-space justify="end">
  <n-button @click="router.push('/toes')">{{ t.common.cancel }}</n-button>
  <n-button type="primary" @click="goStep2">{{ t.toe.nextStep }}</n-button>
</n-space>
</div>

<!-- Step 2: Review & edit with optional AI generation -->
<div v-if="currentStep === 2">
<div v-if="aiGenerating" style="text-align: center; padding: 60px 0">
  <n-spin size="large" />
  <n-text depth="3" style="display: block; margin-top: 16px">{{ t.toe.aiGeneratingDesc }}</n-text>
</div>
<div v-else>
  <n-form :model="form" label-placement="top">
    <n-grid :cols="2" :x-gap="16" :y-gap="4">

      <!-- AI Generate Button Container -->
      <n-gi :span="2">
        <div style="display: flex; gap: 8px">
          <n-button type="primary" :loading="aiGenerating" @click="generateDescription">{{ t.common.aiGenerate }}</n-button>
          <n-text v-if="aiError" type="error">{{ aiError }}</n-text>
        </div>
      </n-gi>

      <!-- TOE Type -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.toeTypeDesc" subtitle="What type of product is this TOE?" />
          </template>
          <n-input v-model:value="form.toe_type_desc" type="textarea" autosize :placeholder="t.toe.toeTypeDesc" />
        </n-form-item>
      </n-gi>

      <!-- TOE Usage -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.toeUsage" subtitle="How is the TOE typically used?" />
          </template>
          <n-input v-model:value="form.toe_usage" type="textarea" autosize :placeholder="t.toe.toeUsage" />
        </n-form-item>
      </n-gi>

      <!-- Major Security Features -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.majorSecurityFeatures" subtitle="Main security capabilities" />
          </template>
          <n-input v-model:value="form.major_security_features" type="textarea" autosize :placeholder="t.toe.majorSecurityFeatures" />
        </n-form-item>
      </n-gi>

      <!-- Required Non-TOE HW/SW/FW -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.requiredNonToeHwSwFw" subtitle="Non-TOE dependencies" />
          </template>
          <n-input v-model:value="form.required_non_toe_hw_sw_fw" type="textarea" autosize :placeholder="t.toe.requiredNonToeHwSwFw" />
        </n-form-item>
      </n-gi>

      <!-- Physical Scope -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.physicalScope" subtitle="Model, version, firmware that uniquely identifies the TOE" />
          </template>
          <n-input v-model:value="form.physical_scope" type="textarea" autosize :placeholder="t.toe.physicalScope" />
        </n-form-item>
      </n-gi>

      <!-- Logical Scope -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.logicalScope" subtitle="Logical boundaries of security functionality" />
          </template>
          <n-input v-model:value="form.logical_scope" type="textarea" autosize :placeholder="t.toe.logicalScope" />
        </n-form-item>
      </n-gi>

      <!-- HW Interfaces -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.hwInterfaces" subtitle="Physically accessible hardware interfaces" />
          </template>
          <n-input v-model:value="form.hw_interfaces" type="textarea" autosize :placeholder="t.toe.hwInterfaces" />
        </n-form-item>
      </n-gi>

      <!-- SW Interfaces -->
      <n-gi :span="2">
        <n-form-item>
          <template #label>
            <field-label :title="t.toe.swInterfaces" subtitle="Programmatically accessible software interfaces" />
          </template>
          <n-input v-model:value="form.sw_interfaces" type="textarea" autosize :placeholder="t.toe.swInterfaces" />
        </n-form-item>
      </n-gi>

    </n-grid>
  </n-form>
  <n-space justify="end">
    <n-button @click="currentStep = 1">{{ t.toe.prevStep }}</n-button>
    <n-button type="primary" :loading="submitting" @click="handleCreate">{{ t.toe.confirmCreate }}</n-button>
  </n-space>
</div>
</div>
</n-card>
</div>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, type FormInst, type FormRules, NText } from 'naive-ui'
import { toeApi } from '@/api/toes'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
const router = useRouter()
const message = useMessage()

const currentStep = ref(1)
const step1Ref = ref<FormInst | null>(null)
const aiGenerating = ref(false)
const aiError = ref('')
const submitting = ref(false)

const form = ref({
  name: '',
  toe_type: 'software',
  brief_intro: '',
  version: '',
  toe_type_desc: '',
  toe_usage: '',
  major_security_features: '',
  required_non_toe_hw_sw_fw: '',
  physical_scope: '',
  logical_scope: '',
  hw_interfaces: '',
  sw_interfaces: '',
})

const step1Rules: FormRules = {
  name: [{ required: true, message: t.value.toe.toeName + ' is required' }],
  toe_type: [{ required: true, message: t.value.toe.toeType + ' is required' }],
  brief_intro: [{ required: true, message: t.value.toe.briefIntroRequired }],
}

// Inline label component with title + subtitle
const FieldLabel = (props: { title: string; subtitle: string }) =>
  h('div', { style: 'line-height: 1.3' }, [
    h('span', { style: 'font-weight: 500' }, props.title),
    h(NText, { depth: 3, style: 'font-size: 11px; display: block; margin-top: 1px' }, () => props.subtitle),
  ])

async function goStep2() {
  try { await step1Ref.value?.validate() } catch { return }
  currentStep.value = 2
}

async function generateDescription() {
  aiGenerating.value = true
  aiError.value = ''
  try {
    const res = await toeApi.aiGenerateDescriptionDraft({
      name: form.value.name,
      toe_type: form.value.toe_type,
      brief_intro: form.value.brief_intro,
      version: form.value.version || undefined,
      language: localeStore.lang,
    })
    const d = res.data
    if (d.toe_type_desc) form.value.toe_type_desc = d.toe_type_desc
    if (d.toe_usage) form.value.toe_usage = d.toe_usage
    if (d.major_security_features) form.value.major_security_features = d.major_security_features
    if (d.required_non_toe_hw_sw_fw) form.value.required_non_toe_hw_sw_fw = d.required_non_toe_hw_sw_fw
    if (d.physical_scope) form.value.physical_scope = d.physical_scope
    if (d.logical_scope) form.value.logical_scope = d.logical_scope
    if (d.hw_interfaces) form.value.hw_interfaces = d.hw_interfaces
    if (d.sw_interfaces) form.value.sw_interfaces = d.sw_interfaces
  } catch (e: any) {
    aiError.value = e.message || t.value.toe.aiGenerateFailed
  } finally {
    aiGenerating.value = false
  }
}

async function handleCreate() {
  submitting.value = true
  try {
    const res = await toeApi.create({
      name: form.value.name,
      toe_type: form.value.toe_type,
      brief_intro: form.value.brief_intro,
      version: form.value.version || undefined,
      toe_type_desc: form.value.toe_type_desc || undefined,
      toe_usage: form.value.toe_usage || undefined,
      major_security_features: form.value.major_security_features || undefined,
      required_non_toe_hw_sw_fw: form.value.required_non_toe_hw_sw_fw || undefined,
      physical_scope: form.value.physical_scope || undefined,
      logical_scope: form.value.logical_scope || undefined,
      hw_interfaces: form.value.hw_interfaces || undefined,
      sw_interfaces: form.value.sw_interfaces || undefined,
    })
    message.success(t.value.toe.createdSuccess)
    router.push(`/toes/${res.data.id}`)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
