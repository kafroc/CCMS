<template>
<div v-if="toe">
<n-page-header :title="toe.name" @back="router.push('/toes')">
<template #subtitle>
<n-space :size="8" align="center">
<n-tag :type="(typeTagMap[toe.toe_type] || 'default') as any" size="small">
{{ typeLabel[toe.toe_type] || toe.toe_type }}
</n-tag>
<n-space :size="4" align="center">
<n-text v-if="toe.version" depth="3" style="font-size: 13px">{{ toe.version }}</n-text>
<n-button 
  v-if="canWrite"
  size="tiny"
  type="tertiary"
  @click="editVersionHandler"
  style="padding: 0 4px; height: auto; min-height: auto"
>✏️</n-button>
</n-space>
</n-space>
</template>
<template #extra>
</template>
</n-page-header>

<n-tabs type="line" style="margin-top: 16px" v-model:value="activeTab">

<!-- ══════════════════════════════════
     Overview Tab
════════════════════════════════════ -->
<n-tab-pane name="overview" :tab="t.toe.overview">
<div style="display: flex; justify-content: flex-start; gap: 8px; margin-bottom: 12px">
  <n-button
    v-if="!editingOverview && canWrite"
    size="small"
    @click="startEditingOverview"
  >✏️ {{ t.common.edit }}</n-button>
  <n-space v-else-if="canWrite" :size="8">
    <n-button
      size="small"
      :loading="overviewEditSaving"
      @click="saveOverview"
    >✓ {{ t.common.save }}</n-button>
    <n-button size="small" @click="cancelEditingOverview" :disabled="overviewEditSaving">✕ {{ t.common.cancel }}</n-button>
    <n-divider vertical />
    <n-button
      size="small"
      :loading="consolidating"
      :title="t.toe.aiConsolidateDesc"
      @click="handleConsolidate"
    >
      ✦ {{ t.toe.aiConsolidate }}
    </n-button>
  </n-space>
  <n-button
    v-if="!editingOverview && canWrite"
    size="small"
    :loading="consolidating"
    :title="t.toe.aiConsolidateDesc"
    @click="handleConsolidate"
  >
    ✦ {{ t.toe.aiConsolidate }}
  </n-button>
  <n-button
    v-if="canWrite"
    size="small"
    :loading="translatingOverview"
    @click="translateAllFieldsWithReview"
    :title="t.toe.translateAllTitle"
  >🌐 {{ t.toe.translateAll }}</n-button>
</div>
<div class="overview-grid">

  <!-- Brief Intro (visible in both modes) -->
  <div class="overview-section full-width">
    <div class="section-header">
      <span class="section-icon">📝</span>
      <span class="section-title">{{ t.toe.briefIntro }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('brief_intro')"
          @click="handleConsolidateField('brief_intro')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'brief_intro'"
          @click="translateSingleField('brief_intro')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.brief_intro">{{ toe.brief_intro }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.brief_intro"
          type="textarea"
          :rows="2"
          :autosize="{ minRows: 2 }"
          :placeholder="t.toe.briefIntroPlaceholder"
        />
      </template>
    </div>
  </div>

  <!-- Row 1: TOE Type (full width) -->
  <div class="overview-section full-width">
    <div class="section-header">
      <span class="section-icon">🏷</span>
      <span class="section-title">{{ t.toe.toeTypeDesc }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('toe_type_desc')"
          @click="handleConsolidateField('toe_type_desc')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'toe_type_desc'"
          @click="translateSingleField('toe_type_desc')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.toe_type_desc">{{ toe.toe_type_desc }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.toe_type_desc"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.toeTypeDescPlaceholder"
        />
      </template>
    </div>
  </div>

  <!-- Row 2: Usage + Security Features (2 cols) -->
  <div class="overview-section">
    <div class="section-header">
      <span class="section-icon">⚙</span>
      <span class="section-title">{{ t.toe.toeUsage }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('toe_usage')"
          @click="handleConsolidateField('toe_usage')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'toe_usage'"
          @click="translateSingleField('toe_usage')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.toe_usage">{{ toe.toe_usage }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.toe_usage"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.toeUsagePlaceholder"
        />
      </template>
    </div>
  </div>

  <div class="overview-section">
    <div class="section-header">
      <span class="section-icon">🔒</span>
      <span class="section-title">{{ t.toe.majorSecurityFeatures }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('major_security_features')"
          @click="handleConsolidateField('major_security_features')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'major_security_features'"
          @click="translateSingleField('major_security_features')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.major_security_features">{{ toe.major_security_features }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.major_security_features"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.majorSecurityFeaturesPlaceholder"
        />
      </template>
    </div>
  </div>

  <!-- Row 3: Required Non-TOE (full width) -->
  <div class="overview-section full-width">
    <div class="section-header">
      <span class="section-icon">📦</span>
      <span class="section-title">{{ t.toe.requiredNonToeHwSwFw }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('required_non_toe_hw_sw_fw')"
          @click="handleConsolidateField('required_non_toe_hw_sw_fw')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'required_non_toe_hw_sw_fw'"
          @click="translateSingleField('required_non_toe_hw_sw_fw')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.required_non_toe_hw_sw_fw">{{ toe.required_non_toe_hw_sw_fw }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.required_non_toe_hw_sw_fw"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.requiredNonToePlaceholder"
        />
      </template>
    </div>
  </div>

  <!-- Row 4: Physical Scope + Logical Scope (2 cols) -->
  <div class="overview-section">
    <div class="section-header">
      <span class="section-icon">📐</span>
      <span class="section-title">{{ t.toe.physicalScope }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('physical_scope')"
          @click="handleConsolidateField('physical_scope')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'physical_scope'"
          @click="translateSingleField('physical_scope')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.physical_scope">{{ toe.physical_scope }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.physical_scope"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.physicalScopePlaceholder"
        />
      </template>
    </div>
  </div>

  <div class="overview-section">
    <div class="section-header">
      <span class="section-icon">🔷</span>
      <span class="section-title">{{ t.toe.logicalScope }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('logical_scope')"
          @click="handleConsolidateField('logical_scope')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'logical_scope'"
          @click="translateSingleField('logical_scope')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.logical_scope">{{ toe.logical_scope }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.logical_scope"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.logicalScopePlaceholder"
        />
      </template>
    </div>
  </div>

  <!-- Row 5: HW Interfaces + SW Interfaces (2 cols) -->
  <div class="overview-section">
    <div class="section-header">
      <span class="section-icon">🔌</span>
      <span class="section-title">{{ t.toe.hwInterfaces }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('hw_interfaces')"
          @click="handleConsolidateField('hw_interfaces')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'hw_interfaces'"
          @click="translateSingleField('hw_interfaces')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.hw_interfaces">{{ toe.hw_interfaces }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.hw_interfaces"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.hwInterfacesPlaceholder"
        />
      </template>
    </div>
  </div>

  <div class="overview-section">
    <div class="section-header">
      <span class="section-icon">💻</span>
      <span class="section-title">{{ t.toe.swInterfaces }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="consolidatingFields.includes('sw_interfaces')"
          @click="handleConsolidateField('sw_interfaces')"
        >✦ AI</n-button>
        <n-button
          v-if="!editingOverview && canWrite"
          size="tiny"
          :loading="translatingField === 'sw_interfaces'"
          @click="translateSingleField('sw_interfaces')"
        >🌐</n-button>
      </div>
    </div>
    <div class="section-body">
      <template v-if="!editingOverview">
        <n-text v-if="toe.sw_interfaces">{{ toe.sw_interfaces }}</n-text>
        <n-text depth="3" v-else>—</n-text>
      </template>
      <template v-else>
        <n-input 
          v-model:value="overviewEditData.sw_interfaces"
          type="textarea"
          :rows="3"
          :autosize="{ minRows: 3 }"
          :placeholder="t.toe.swInterfacesPlaceholder"
        />
      </template>
    </div>
  </div>

</div>
</n-tab-pane>

<!-- ══════════════════════════════════
     Assets Tab
════════════════════════════════════ -->
<n-tab-pane name="assets" :tab="`${t.toe.assets} (${assets.length})`">
<n-space justify="end" style="margin-bottom: 12px">
<n-button v-if="canWrite && selectedAssetIds.length > 0" size="small" :style="{ backgroundColor: '#fff', color: '#000', border: '1px solid #ccc' }" :loading="batchDeleting" @click="batchDeleteAssets">
  {{ t.common.delete }} ({{ selectedAssetIds.length }})
</n-button>
<n-button v-if="canWrite" size="small" :style="{ backgroundColor: '#fff', color: '#000', border: '1px solid #ccc' }" @click="openAssetDrawer()">
  <template #icon><n-icon><AddOutline /></n-icon></template>
  {{ t.toe.addAsset }}
</n-button>
<n-button v-if="canWrite" size="small" :style="{ backgroundColor: '#fff', color: '#000', border: '1px solid #ccc' }" :loading="aiSuggesting" @click="handleAiSuggest">
  ✦ {{ t.toe.aiSuggestAssets }}
</n-button>
</n-space>

<n-data-table
  :columns="assetColumns"
  :data="assets"
  :loading="assetsLoading"
  :row-key="(r: any) => r.id"
  :scroll-x="860"
  v-model:checked-row-keys="selectedAssetIds"
/>

<n-card v-if="aiSuggestions.length > 0" :title="t.toe.aiSuggestAssets" style="margin-top: 16px" size="small">
<n-list>
  <n-list-item v-for="(s, i) in aiSuggestions" :key="i">
    <n-thing :title="s.name" :description="s.description">
      <template #header-extra>
        <n-space :size="8">
          <n-tag size="small">{{ (t.toe.assetTypes as any)[s.asset_type] || s.asset_type }}</n-tag>
          <n-rate :value="s.importance" readonly size="small" />
        </n-space>
      </template>
    </n-thing>
    <template #suffix>
      <n-space v-if="canWrite">
        <n-button size="small" type="primary" @click="acceptSuggestion(s)">{{ t.threat.adopt }}</n-button>
        <n-button size="small" @click="aiSuggestions.splice(i, 1)">{{ t.threat.ignore }}</n-button>
      </n-space>
    </template>
  </n-list-item>
</n-list>
</n-card>
</n-tab-pane>

<!-- ══════════════════════════════════
     TOE Documents Tab
════════════════════════════════════ -->
<n-tab-pane name="toe-docs" :tab="`${t.toe.toeDocuments} (${toeDocFiles.length})`">
<n-alert type="info" :show-icon="false" style="margin-bottom: 12px">{{ t.toe.toeDocumentsHint }}</n-alert>
<n-upload v-if="canWrite" multiple :custom-request="(opts: any) => handleFileUpload(opts, 'manual')" :show-file-list="false" style="margin-bottom: 12px">
  <n-upload-dragger>
    <div style="padding: 20px 0">
      <n-icon size="40" :depth="3"><CloudUploadOutline /></n-icon>
      <n-text depth="3" style="display: block; margin-top: 8px">{{ t.toe.uploadHint }}</n-text>
    </div>
  </n-upload-dragger>
</n-upload>
<n-data-table :columns="toeDocColumns" :data="toeDocFiles" :loading="filesLoading" :row-key="(r: any) => r.id" />
<n-empty v-if="!filesLoading && toeDocFiles.length === 0" :description="t.toe.noFiles" style="margin-top: 24px" />
</n-tab-pane>

<!-- ══════════════════════════════════
     ST/PP Documents Tab
════════════════════════════════════ -->
<n-tab-pane name="st-pp-docs" :tab="`${t.toe.stPpDocuments} (${stPpFiles.length})`">
<n-alert type="info" :show-icon="false" style="margin-bottom: 12px">{{ t.toe.stPpDocumentsHint }}</n-alert>
<n-upload v-if="canWrite" multiple :custom-request="(opts: any) => handleFileUpload(opts, 'st_pp')" :show-file-list="false" style="margin-bottom: 12px">
  <n-upload-dragger>
    <div style="padding: 20px 0">
      <n-icon size="40" :depth="3"><CloudUploadOutline /></n-icon>
      <n-text depth="3" style="display: block; margin-top: 8px">{{ t.toe.uploadHint }}</n-text>
    </div>
  </n-upload-dragger>
</n-upload>
<n-data-table :columns="stPpDocColumns" :data="stPpFiles" :loading="filesLoading" :row-key="(r: any) => r.id" />
<n-empty v-if="!filesLoading && stPpFiles.length === 0" :description="t.toe.noFiles" style="margin-top: 24px" />
</n-tab-pane>

</n-tabs>

<!-- ══════════════════════════════════
     Edit Drawer
════════════════════════════════════ -->
<n-drawer v-model:show="showEditDrawer" :width="620" placement="right">
<n-drawer-content :title="t.toe.editBasicInfo" closable>
<n-form :model="editForm" label-placement="top" :label-width="'auto'" :disabled="!canWrite">
  <!-- Identity row -->
  <n-grid :cols="2" :x-gap="16">
    <n-gi>
      <n-form-item :label="t.toe.toeName">
        <n-input v-model:value="editForm.name" />
      </n-form-item>
    </n-gi>
    <n-gi>
      <n-form-item :label="t.toe.version">
        <n-input v-model:value="editForm.version" />
      </n-form-item>
    </n-gi>
    <n-gi :span="2">
      <n-form-item :label="t.toe.toeType">
        <n-radio-group v-model:value="editForm.toe_type">
          <n-space>
            <n-radio value="hardware">{{ t.toe.hardware }}</n-radio>
            <n-radio value="software">{{ t.toe.software }}</n-radio>
            <n-radio value="system">{{ t.toe.system }}</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
    </n-gi>
    <n-gi :span="2">
      <n-form-item :label="t.toe.briefIntro">
        <n-input v-model:value="editForm.brief_intro" type="textarea" :rows="2" />
      </n-form-item>
    </n-gi>
  </n-grid>

  <n-divider style="margin: 8px 0" />

  <!-- 8 content fields -->
  <template v-for="field in editFields" :key="field.key">
    <n-form-item>
      <template #label>
        <div class="edit-label">
          <span>{{ field.label }}</span>
          <n-text depth="3" style="font-size: 11px">{{ field.sub }}</n-text>
          <n-button
            v-if="canWrite"
            size="tiny"
            style="margin-left: auto"
            :loading="fieldGenerating === field.key"
            @click="aiField(field.key)"
          >✦ AI</n-button>
        </div>
      </template>
      <n-input v-model:value="editForm[field.key]" type="textarea" :rows="field.rows" />
    </n-form-item>
  </template>
</n-form>
<template #footer>
<n-space justify="end">
  <n-button @click="showEditDrawer = false">{{ t.common.cancel }}</n-button>
  <n-button v-if="canWrite" type="primary" :loading="editSaving" @click="saveEdit">{{ t.common.save }}</n-button>
</n-space>
</template>
</n-drawer-content>
</n-drawer>

<!-- Asset Drawer -->
<n-drawer v-model:show="showAssetDrawer" :width="480" placement="right">
<n-drawer-content :title="editingAssetId ? t.toe.editAsset : t.toe.addAsset" closable>
<n-form ref="assetFormRef" :model="assetForm" :rules="assetRules" label-placement="top" :disabled="!canWrite">
  <n-form-item :label="t.toe.assetName" path="name">
    <n-input v-model:value="assetForm.name" />
  </n-form-item>
  <n-form-item :label="t.toe.assetType" path="asset_type">
    <n-select v-model:value="assetForm.asset_type" :options="assetTypeOptions" />
  </n-form-item>
  <n-form-item :label="t.toe.assetDescription">
    <n-input
      v-model:value="assetForm.description"
      type="textarea"
      :rows="4"
      :placeholder="t.toe.assetDescriptionPlaceholder"
      style="white-space: pre-wrap; word-break: break-word"
    />
  </n-form-item>
  <n-form-item :label="t.toe.assetImportance" path="importance">
    <n-rate v-model:value="assetForm.importance" :count="5" />
    <n-text depth="3" style="margin-left: 8px; font-size: 12px">
      {{ (t.toe.importanceLabels as any)[assetForm.importance] || '' }}
    </n-text>
  </n-form-item>
  <n-form-item :label="t.toe.assetImportanceReason">
    <n-input v-model:value="assetForm.importance_reason" type="textarea" :rows="2" />
  </n-form-item>
  <n-form-item :label="t.toe.relatedThreats">
    <n-select
      v-model:value="selectedThreatIds"
      :options="relatedThreats.map(t => ({ label: t.code, value: t.id }))"
      multiple
      clearable
      filterable
      :placeholder="t.toe.relatedThreatsPlaceholder"
    />
  </n-form-item>
</n-form>
<template #footer>
<n-space justify="end">
  <n-button @click="showAssetDrawer = false">{{ t.common.cancel }}</n-button>
  <n-button v-if="canWrite" type="primary" :loading="assetSaving" @click="saveAsset">
    {{ editingAssetId ? t.common.save : t.common.create }}
  </n-button>
</n-space>
</template>
</n-drawer-content>
</n-drawer>

<!-- AI Extraction Preview Modal -->
<n-modal v-model:show="showAnalysisPreview" :mask-closable="false" style="max-width: 680px; width: 95vw">
<n-card :title="t.toe.aiAnalyzePreviewTitle" :bordered="false" size="medium" role="dialog">
  <n-alert type="info" :show-icon="false" style="margin-bottom: 16px; font-size: 13px">
    {{ t.toe.aiAnalyzePreviewDesc }}
  </n-alert>
  <div v-for="(val, key) in pendingAnalysis" :key="key" style="margin-bottom: 16px">
    <div style="font-weight: 500; font-size: 13px; margin-bottom: 4px; color: #555">
      {{ fieldLabelMap[key] || key }}
    </div>
    <n-input
      :value="val"
      type="textarea"
      :rows="5"
      readonly
      style="font-size: 12px; font-family: inherit"
    />
  </div>
  <template #footer>
    <n-space justify="end">
      <n-button @click="cancelAnalysis">{{ t.common.cancel }}</n-button>
      <n-button v-if="canWrite" type="primary" :loading="applyingAnalysis" @click="confirmAnalysis">
        {{ t.toe.aiAnalyzeConfirm }}
      </n-button>
    </n-space>
  </template>
</n-card>
</n-modal>

<!-- Field Consolidate Review Modal -->
<n-modal v-model:show="showConsolidateReview" :mask-closable="false" style="max-width: 700px; width: 95vw">
<n-card :title="`${t.toe.reviewAiConsolidation} - ${labelForField(consolidateReviewField)}`" :bordered="false" size="medium" role="dialog">
  <n-alert type="warning" :show-icon="false" style="margin-bottom: 16px; font-size: 13px">
    {{ t.toe.reviewAiConsolidationDesc }}
  </n-alert>
  <n-input
    :value="consolidateReviewContent"
    type="textarea"
    :rows="8"
    readonly
    style="font-size: 12px; font-family: inherit; margin-bottom: 16px"
  />
  <n-space justify="space-between">
    <div style="font-size: 12px; color: #999">
      {{ t.toe.currentValue }}: {{ (toe as any)?.[consolidateReviewField || '']?.slice(0, 50) || t.toe.emptyValue }}...
    </div>
  </n-space>
  <template #footer>
    <n-space justify="end">
      <n-button @click="cancelConsolidateReview">{{ t.common.cancel }}</n-button>
      <n-button v-if="canWrite" type="primary" :loading="reviewingConsolidate" @click="confirmConsolidateReview">
        ✓ {{ t.toe.confirmReplace }}
      </n-button>
    </n-space>
  </template>
</n-card>
</n-modal>

<!-- Translation Review Modal -->
<n-modal v-model:show="showTranslateReview" :mask-closable="false" style="max-width: 700px; width: 95vw">
<n-card :title="`${t.toe.reviewTranslation} - ${labelForField(translateReviewField)}`" :bordered="false" size="medium" role="dialog">
  <n-alert type="info" :show-icon="false" style="margin-bottom: 16px; font-size: 13px">
    {{ t.toe.translationReviewDesc }}
  </n-alert>
  <div style="margin-bottom: 16px">
    <n-text strong style="margin-bottom: 8px; display: block">{{ t.toe.translationOriginal }}:</n-text>
    <n-input
      :value="overviewEditData[translateReviewField || '']"
      type="textarea"
      :rows="5"
      readonly
      style="font-size: 12px; font-family: inherit; margin-bottom: 8px"
    />
  </div>
  <div style="margin-bottom: 16px">
    <n-text strong style="margin-bottom: 8px; display: block">{{ t.toe.translationResult }}:</n-text>
    <n-input
      v-model:value="translateReviewContent"
      type="textarea"
      :rows="5"
      style="font-size: 12px; font-family: inherit"
    />
  </div>
  <template #footer>
    <n-space justify="end">
      <n-button @click="cancelTranslation">{{ t.common.cancel }}</n-button>
      <n-button v-if="canWrite" type="primary" :loading="confirmingTranslate" @click="confirmTranslation">
        ✓ {{ t.toe.confirmApply }}
      </n-button>
    </n-space>
  </template>
</n-card>
</n-modal>

<!-- All Fields Translation Review Modal -->
<n-modal v-model:show="showAllFieldsTranslateReview" :mask-closable="false" size="large" style="max-width: 900px; width: 95vw">
<n-card :title="t.toe.reviewAllTranslations" :bordered="false" size="medium" role="dialog">
  <n-alert type="info" :show-icon="false" style="margin-bottom: 16px; font-size: 13px">
    {{ t.toe.translationReviewDesc }}
  </n-alert>
  <n-scrollbar style="max-height: 500px">
    <div v-for="(translatedValue, field) in allFieldsTranslatedData" :key="field" style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e0e0e0">
      <n-text strong style="margin-bottom: 8px; display: block">{{ fieldLabelMap[field as string] || field }}</n-text>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px">
        <div>
          <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 4px">{{ t.toe.translationOriginal }}:</n-text>
          <n-input
            :value="overviewEditData[field as string]"
            type="textarea"
            :rows="3"
            readonly
            style="font-size: 12px; font-family: inherit"
          />
        </div>
        <div>
          <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 4px">{{ t.toe.translationResult }}:</n-text>
          <n-input
            v-model:value="allFieldsTranslatedData[field as string]"
            type="textarea"
            :rows="3"
            style="font-size: 12px; font-family: inherit"
          />
        </div>
      </div>
    </div>
  </n-scrollbar>
  <template #footer>
    <n-space justify="end">
      <n-button @click="cancelAllFieldsTranslation">{{ t.common.cancel }}</n-button>
      <n-button v-if="canWrite" type="primary" :loading="confirmingAllFieldsTranslate" @click="confirmAllFieldsTranslation">
        ✓ {{ t.toe.confirmApplyAll }}
      </n-button>
    </n-space>
  </template>
</n-card>
</n-modal>

</div>
<div v-else style="padding-top: 80px; text-align: center">
<n-spin v-if="pageLoading" size="large" />
<n-result v-else status="404" :title="t.common.noData" />
</div>
</template>

<script setup lang="ts">
import { ref, h, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NSpace, NTag, NTooltip, NIcon, NDivider,
  useMessage, useDialog,
  type FormInst, type FormRules, type DataTableColumns,
} from 'naive-ui'
import { AddOutline, CloudUploadOutline } from '@vicons/ionicons5'
import { toeApi, type TOE, type TOEAsset, type TOEFile } from '@/api/toes'
import { threatApi, type Threat } from '@/api/threats'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const toeId = route.params.id as string

const toe = ref<TOE | null>(null)
const pageLoading = ref(true)
const activeTab = ref(typeof route.query.tab === 'string' ? route.query.tab : 'overview')
const canWrite = computed(() => toe.value?.access_level !== 'read')

const typeLabel = computed<Record<string, string>>(() => ({
  hardware: t.value.toe.hardware,
  software: t.value.toe.software,
  system: t.value.toe.system,
}))
const typeTagMap: Record<string, string> = { hardware: 'info', software: 'success', system: 'warning' }

// ── Edit drawer ──
const showEditDrawer = ref(false)
const editForm = ref<Record<string, any>>({})
const editSaving = ref(false)
const fieldGenerating = ref('')

const editFields = computed(() => [
  { key: 'toe_type_desc',           label: t.value.toe.toeTypeDesc,          sub: 'What type of product is this TOE?',                        rows: 3 },
  { key: 'toe_usage',               label: t.value.toe.toeUsage,              sub: 'How is the TOE typically deployed and used?',               rows: 3 },
  { key: 'major_security_features', label: t.value.toe.majorSecurityFeatures, sub: 'Main security capabilities of the TOE',                     rows: 3 },
  { key: 'required_non_toe_hw_sw_fw', label: t.value.toe.requiredNonToeHwSwFw, sub: 'Non-TOE components the TOE depends on',                    rows: 3 },
  { key: 'physical_scope',          label: t.value.toe.physicalScope,          sub: 'Model, version, firmware that uniquely identifies the TOE', rows: 3 },
  { key: 'logical_scope',           label: t.value.toe.logicalScope,           sub: 'Logical boundaries of TOE security functionality',          rows: 3 },
  { key: 'hw_interfaces',           label: t.value.toe.hwInterfaces,           sub: 'Physically accessible hardware interfaces',                 rows: 3 },
  { key: 'sw_interfaces',           label: t.value.toe.swInterfaces,           sub: 'Programmatically accessible software interfaces',           rows: 3 },
])

// ── AI analyze single file ──
const analyzingFileId = ref<string | null>(null)
const consolidating = ref(false)
const consolidatingFields = ref<string[]>([])

// AI extraction preview
const showAnalysisPreview = ref(false)
const pendingAnalysis = ref<Record<string, string>>({})
const applyingAnalysis = ref(false)

// ── Field consolidate review ──
const showConsolidateReview = ref(false)
const consolidateReviewField = ref<string | null>(null)
const consolidateReviewContent = ref<string>('')
const reviewingConsolidate = ref(false)

// ── Overview inline editing ──
const editingOverview = ref(false)
const overviewEditData = ref<Record<string, any>>({})
const overviewEditSaving = ref(false)
const translatingOverview = ref(false)
const translatingField = ref<string | null>(null)

// ── Translation review ──
const showTranslateReview = ref(false)
const translateReviewField = ref<string | null>(null)
const translateReviewContent = ref<string>('')
const confirmingTranslate = ref(false)

// ── All fields translation review ──
const showAllFieldsTranslateReview = ref(false)
const allFieldsTranslatedData = ref<Record<string, string>>({})
const confirmingAllFieldsTranslate = ref(false)

// Map field keys to display labels (computed with i18n support)
const fieldLabelMap = computed<Record<string, string>>(() => ({
  brief_intro: t.value.toe.briefIntro,
  toe_type: t.value.toe.toeType,
  toe_type_desc: t.value.toe.toeTypeDesc,
  toe_usage: t.value.toe.toeUsage,
  toe_description: t.value.toe.toeDescription,
  major_security_features: t.value.toe.majorSecurityFeatures,
  required_non_toe_hw_sw_fw: t.value.toe.requiredNonToeHwSwFw,
  physical_scope: t.value.toe.physicalScope,
  logical_scope: t.value.toe.logicalScope,
  hw_interfaces: t.value.toe.hwInterfaces,
  sw_interfaces: t.value.toe.swInterfaces,
}))

function labelForField(field: string | null) {
  if (!field) return ''
  return fieldLabelMap.value[field] || field
}

// ── Assets ──
const assets = ref<TOEAsset[]>([])
const assetsLoading = ref(false)
const selectedAssetIds = ref<string[]>([])
const batchDeleting = ref(false)
const showAssetDrawer = ref(false)
const assetFormRef = ref<FormInst | null>(null)
const editingAssetId = ref<string | null>(null)
const assetSaving = ref(false)
const relatedThreats = ref<Threat[]>([])
const aiSuggesting = ref(false)
const aiSuggestions = ref<any[]>([])
const assetForm = ref({ name: '', description: '', asset_type: 'data', importance: 3, importance_reason: '', asset_ids: [] as string[] })
const selectedThreatIds = ref<string[]>([])
const assetThreatMap = computed<Record<string, Threat[]>>(() => {
  const mapping: Record<string, Threat[]> = {}
  for (const threat of relatedThreats.value) {
    for (const assetId of threat.asset_ids || []) {
      if (!mapping[assetId]) {
        mapping[assetId] = []
      }
      mapping[assetId].push(threat)
    }
  }
  return mapping
})

const assetTypeOptions = computed(() => [
  { label: (t.value.toe.assetTypes as any).data, value: 'data' },
  { label: (t.value.toe.assetTypes as any).function, value: 'function' },
  { label: (t.value.toe.assetTypes as any).privacy, value: 'privacy' },
  { label: (t.value.toe.assetTypes as any).config, value: 'config' },
  { label: (t.value.toe.assetTypes as any).other, value: 'other' },
])
const assetRules: FormRules = {
  name: [{ required: true, message: t.value.toe.assetName + ' is required' }],
  asset_type: [{ required: true, message: t.value.toe.assetType + ' is required' }],
}

const assetColumns = computed<DataTableColumns<TOEAsset>>(() => [
  {
    title: '',
    type: 'selection',
    width: 40,
    disabled: (r) => !canWrite.value,
  },
  { title: t.value.toe.assetName, key: 'name', width: 200, ellipsis: { tooltip: true } },
  { title: t.value.toe.assetType, key: 'asset_type', width: 100, render: (r) => (t.value.toe.assetTypes as any)[r.asset_type] || r.asset_type },
  {
    title: t.value.toe.assetImportance, key: 'importance', width: 130,
    render: (r) => h('span', { title: r.importance_reason || '', style: { cursor: r.importance_reason ? 'help' : 'default', letterSpacing: '2px' } },
      '★'.repeat(r.importance) + '☆'.repeat(5 - r.importance))
  },
  {
    title: t.value.toe.assetDescription, key: 'description', width: 280,
    ellipsis: false,
    render: (r) => h('div', {
      style: {
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        lineHeight: '1.5',
        maxHeight: '100px',
        overflow: 'auto',
        padding: '4px 0',
      }
    }, r.description || '-')
  },
  {
    title: t.value.toe.relatedThreats,
    key: 'related_threats',
    width: 240,
    render: (r) => {
      const threats = assetThreatMap.value[r.id] || []
      if (!threats.length) {
        return h('span', { style: 'color:#999' }, '-')
      }
      return h(NSpace, { size: 'small', wrap: true }, {
        default: () => threats.map((threat) => h(NButton, {
          size: 'tiny',
          tertiary: true,
          onClick: () => goToThreat(threat.id),
        }, { default: () => threat.code }))
      })
    }
  },
  {
    title: t.value.toe.source, key: 'ai_generated', width: 80,
    titleAlign: 'center',
    align: 'center',
    render: (r) => r.ai_generated
      ? h(NTag, { size: 'small', type: 'info' }, { default: () => 'AI' })
      : h(NTag, { size: 'small' }, { default: () => t.value.toe.manual })
  },

  {
    title: t.value.toe.operation, key: 'actions', width: 140, fixed: 'right',
    render: (r) => h(NSpace, { size: 'small' }, { default: () => [
      h(NButton, { size: 'small', onClick: () => openAssetDrawer(r) }, { default: () => t.value.common.edit }),
      ...(canWrite.value ? [h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => deleteAsset(r) }, { default: () => t.value.common.delete })] : []),
    ]})
  },
])

// ── Files ──
const files = ref<TOEFile[]>([])
const filesLoading = ref(false)
let filePollingTimers: number[] = []

const toeDocFiles = computed(() => files.value.filter(f => f.file_category !== 'st_pp'))
const stPpFiles = computed(() => files.value.filter(f => f.file_category === 'st_pp'))

function makeFileColumns(focus: 'st_pp' | 'manual'): DataTableColumns<TOEFile> {
  return [
    { title: t.value.toe.fileName, key: 'original_filename', ellipsis: { tooltip: true } },
    { title: t.value.toe.fileSize, key: 'file_size', width: 90, render: (r) => formatFileSize(r.file_size) },
    {
      title: t.value.toe.processStatus, key: 'process_status', width: 110,
      render: (r) => {
        const map: Record<string, { type: string; label: string }> = {
          pending:    { type: 'default', label: (t.value.toe.processStatuses as any).pending },
          processing: { type: 'warning', label: (t.value.toe.processStatuses as any).processing },
          ready:      { type: 'success', label: (t.value.toe.processStatuses as any).ready },
          failed:     { type: 'error',   label: (t.value.toe.processStatuses as any).failed },
        }
        const s = map[r.process_status] || { type: 'default', label: r.process_status }
        return h(NTooltip, { disabled: !r.process_error }, {
          trigger: () => h(NTag, { type: s.type as any, size: 'small' }, { default: () => s.label }),
          default: () => r.process_error || '',
        })
      }
    },
    {
      title: t.value.toe.operation, key: 'actions', width: 160,
      render: (r) => h(NSpace, { size: 'small' }, { default: () => [
        ...(canWrite.value ? [
          h(NButton, {
            size: 'small',
            type: 'primary',
            ghost: true,
            disabled: r.process_status !== 'ready',
            loading: analyzingFileId.value === r.id,
            onClick: () => handleAnalyzeFile(r, focus),
          }, { default: () => '✦ AI' }),
          h(NButton, {
            size: 'small', type: 'error', ghost: true,
            onClick: () => deleteFile(r),
          }, { default: () => t.value.common.delete }),
        ] : []),
      ]})
    },
  ]
}

const toeDocColumns = computed(() => makeFileColumns('manual'))
const stPpDocColumns = computed(() => makeFileColumns('st_pp'))

function formatFileSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// ── Data loading ──
async function loadToe() {
  try {
    const res = await toeApi.get(toeId)
    toe.value = res.data
    editForm.value = { ...res.data }
    // Initialize overview edit data
    overviewEditData.value = {
      brief_intro: res.data.brief_intro || '',
      toe_type_desc: res.data.toe_type_desc || '',
      toe_usage: res.data.toe_usage || '',
      major_security_features: res.data.major_security_features || '',
      required_non_toe_hw_sw_fw: res.data.required_non_toe_hw_sw_fw || '',
      physical_scope: res.data.physical_scope || '',
      logical_scope: res.data.logical_scope || '',
      hw_interfaces: res.data.hw_interfaces || '',
      sw_interfaces: res.data.sw_interfaces || '',
    }
  } catch (e: any) {
    message.error(e.message)
  } finally {
    pageLoading.value = false
  }
}

watch(activeTab, (value: string) => {
  router.replace({ query: { ...route.query, tab: value } })
  if (value === 'assets') {
    handleFocusedAsset()
  }
})

watch(() => route.query.tab, (value: unknown) => {
  if (typeof value === 'string' && value !== activeTab.value) {
    activeTab.value = value
  }
})

// ── Overview inline editing functions ──
function startEditingOverview() {
  // Initialize edit data from current toe data
  if (toe.value) {
    overviewEditData.value = {
      brief_intro: toe.value.brief_intro || '',
      toe_type_desc: toe.value.toe_type_desc || '',
      toe_usage: toe.value.toe_usage || '',
      major_security_features: toe.value.major_security_features || '',
      required_non_toe_hw_sw_fw: toe.value.required_non_toe_hw_sw_fw || '',
      physical_scope: toe.value.physical_scope || '',
      logical_scope: toe.value.logical_scope || '',
      hw_interfaces: toe.value.hw_interfaces || '',
      sw_interfaces: toe.value.sw_interfaces || '',
    }
  }
  editingOverview.value = true
}

function cancelEditingOverview() {
  editingOverview.value = false
  // Restore original data
  if (toe.value) {
    overviewEditData.value = {
      brief_intro: toe.value.brief_intro || '',
      toe_type_desc: toe.value.toe_type_desc || '',
      toe_usage: toe.value.toe_usage || '',
      major_security_features: toe.value.major_security_features || '',
      required_non_toe_hw_sw_fw: toe.value.required_non_toe_hw_sw_fw || '',
      physical_scope: toe.value.physical_scope || '',
      logical_scope: toe.value.logical_scope || '',
      hw_interfaces: toe.value.hw_interfaces || '',
      sw_interfaces: toe.value.sw_interfaces || '',
    }
  }
}

function editVersionHandler() {
  // Initialize edit form from current toe data and open drawer
  if (toe.value) {
    editForm.value = { ...toe.value }
    showEditDrawer.value = true
  }
}

async function saveOverview() {
  overviewEditSaving.value = true
  try {
    await toeApi.update(toeId, overviewEditData.value)
    const updated = await toeApi.get(toeId)
    toe.value = updated.data
    editingOverview.value = false
    message.success(t.value.toe.savedSuccess || 'Saved successfully')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    overviewEditSaving.value = false
  }
}

async function translateOverviewToEnglish() {
  translatingOverview.value = true
  try {
    // Prepare content to translate
    const contentToTranslate: Record<string, string> = {}
    for (const [key, value] of Object.entries(overviewEditData.value)) {
      if (value && typeof value === 'string' && value.trim()) {
        contentToTranslate[key] = value
      }
    }
    
    if (Object.keys(contentToTranslate).length === 0) {
      message.info(t.value.toe.translateNoContent)
      return
    }
    
    // Call translation API
    const res = await toeApi.translateToEnglish(contentToTranslate)
    if (res.data && typeof res.data === 'object') {
      // Update edit data with translated content
      for (const [key, translatedValue] of Object.entries(res.data)) {
        if (key in overviewEditData.value) {
          overviewEditData.value[key] = translatedValue
        }
      }
      message.success(t.value.toe.translateCompleted)
    }
  } catch (e: any) {
    message.error(e.message || t.value.toe.translateFailed)
  } finally {
    translatingOverview.value = false
  }
}

async function translateSingleField(field: string) {
  translatingField.value = field
  try {
    const content = overviewEditData.value[field]
    if (!content || typeof content !== 'string' || !content.trim()) {
      message.info(t.value.toe.translateNoContent)
      return
    }
    
    // Call translation API for single field
    const res = await toeApi.translateToEnglish({ [field]: content })
    if (res.data && res.data[field]) {
      const translatedContent = res.data[field]
      // Show review modal
      translateReviewContent.value = translatedContent
      translateReviewField.value = field
      showTranslateReview.value = true
    }
  } catch (e: any) {
    message.error(e.message || t.value.toe.translateFailed)
  } finally {
    translatingField.value = null
  }
}

async function confirmTranslation() {
  if (!translateReviewField.value) return
  confirmingTranslate.value = true
  try {
    const field = translateReviewField.value
    const translatedValue = translateReviewContent.value
    
    // Update overviewEditData for temporary state
    overviewEditData.value[field] = translatedValue
    
    // Save the translation directly to the database
    await toeApi.update(toeId, { [field]: translatedValue })
    
    // Refresh the TOE data to reflect the changes
    const updated = await toeApi.get(toeId)
    toe.value = updated.data
    
    message.success(t.value.toe.translateApplied)
    showTranslateReview.value = false
  } catch (e: any) {
    message.error(e.message || t.value.toe.translateSaveFailed)
  } finally {
    confirmingTranslate.value = false
    translateReviewContent.value = ''
    translateReviewField.value = null
  }
}

async function cancelTranslation() {
  showTranslateReview.value = false
  translateReviewContent.value = ''
  translateReviewField.value = null
}

async function translateAllFieldsWithReview() {
  translatingOverview.value = true
  try {
    // Initialize overviewEditData if not already initialized
    if (Object.keys(overviewEditData.value).length === 0 && toe.value) {
      overviewEditData.value = {
        brief_intro: toe.value.brief_intro || '',
        toe_type_desc: toe.value.toe_type_desc || '',
        toe_usage: toe.value.toe_usage || '',
        major_security_features: toe.value.major_security_features || '',
        required_non_toe_hw_sw_fw: toe.value.required_non_toe_hw_sw_fw || '',
        physical_scope: toe.value.physical_scope || '',
        logical_scope: toe.value.logical_scope || '',
        hw_interfaces: toe.value.hw_interfaces || '',
        sw_interfaces: toe.value.sw_interfaces || '',
      }
    }
    
    // Collect all non-empty fields from overviewEditData
    const contentToTranslate: Record<string, string> = {}
    const fieldsToTranslate = [
      'brief_intro',
      'toe_type_desc',
      'toe_usage',
      'major_security_features',
      'required_non_toe_hw_sw_fw',
      'physical_scope',
      'logical_scope',
      'hw_interfaces',
      'sw_interfaces',
    ]
    
    for (const field of fieldsToTranslate) {
      const value = overviewEditData.value[field]
      if (value && typeof value === 'string' && value.trim()) {
        contentToTranslate[field] = value
      }
    }
    
    if (Object.keys(contentToTranslate).length === 0) {
      message.info(t.value.toe.translateNoContent)
      return
    }
    
    // Call translation API for all fields
    const res = await toeApi.translateToEnglish(contentToTranslate)
    if (res.data && typeof res.data === 'object') {
      allFieldsTranslatedData.value = res.data
      showAllFieldsTranslateReview.value = true
    }
  } catch (e: any) {
    message.error(e.message || t.value.toe.translateFailed)
  } finally {
    translatingOverview.value = false
  }
}

async function confirmAllFieldsTranslation() {
  confirmingAllFieldsTranslate.value = true
  try {
    // Apply all translated content to overviewEditData
    for (const [field, translatedValue] of Object.entries(allFieldsTranslatedData.value)) {
      if (field in overviewEditData.value) {
        overviewEditData.value[field] = translatedValue
      }
    }
    
    // Save all translations to database
    await toeApi.update(toeId, allFieldsTranslatedData.value)
    
    // Refresh the TOE data
    const updated = await toeApi.get(toeId)
    toe.value = updated.data
    
    message.success(t.value.toe.translateAllApplied)
    showAllFieldsTranslateReview.value = false
    allFieldsTranslatedData.value = {}
  } catch (e: any) {
    message.error(e.message || t.value.toe.translateSaveAllFailed)
  } finally {
    confirmingAllFieldsTranslate.value = false
  }
}

async function cancelAllFieldsTranslation() {
  showAllFieldsTranslateReview.value = false
  allFieldsTranslatedData.value = {}
}

async function loadAssets() {
  assetsLoading.value = true
  try {
    const res = await toeApi.listAssets(toeId)
    assets.value = res.data
    handleFocusedAsset()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    assetsLoading.value = false
  }
}

async function loadRelatedThreats() {
  try {
    const res = await threatApi.listThreats(toeId)
    relatedThreats.value = res.data
  } catch (e: any) {
    message.error(e.message)
  }
}

async function loadFiles() {
  filesLoading.value = true
  try {
    const res = await toeApi.listFiles(toeId)
    files.value = res.data
    startFilePolling()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    filesLoading.value = false
  }
}

function startFilePolling() {
  stopFilePolling()
  for (const f of files.value.filter(f => ['pending', 'processing'].includes(f.process_status))) {
    const timer = window.setInterval(async () => {
      try {
        const res = await toeApi.getFileStatus(toeId, f.id)
        const idx = files.value.findIndex(x => x.id === f.id)
        if (idx >= 0) {
          files.value[idx].process_status = res.data.process_status
          files.value[idx].process_error = res.data.process_error
          if (['ready', 'failed'].includes(res.data.process_status)) clearInterval(timer)
        }
      } catch { clearInterval(timer) }
    }, 2000)
    filePollingTimers.push(timer)
  }
}

function stopFilePolling() {
  filePollingTimers.forEach(t => clearInterval(t))
  filePollingTimers = []
}

// ── Edit actions ──
async function saveEdit() {
  editSaving.value = true
  try {
    const res = await toeApi.update(toeId, editForm.value)
    toe.value = res.data
    editForm.value = { ...res.data }
    showEditDrawer.value = false
    message.success(t.value.common.success)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    editSaving.value = false
  }
}

async function aiField(field: string) {
  fieldGenerating.value = field
  try {
    await toeApi.update(toeId, editForm.value)
    const res = await toeApi.aiGenerateDescription(toeId, localeStore.lang)
    if (res.data[field]) {
      editForm.value[field] = res.data[field]
      message.success(t.value.toe.aiFieldComplete)
    }
  } catch (e: any) {
    message.error(e.message)
  } finally {
    fieldGenerating.value = ''
  }
}

// Append extracted value to existing field, separated by divider
function appendField(existing: string | null | undefined, extracted: string): string {
  const cur = (existing || '').trim()
  if (!cur) return extracted
  return cur + '\n\n---\n\n' + extracted
}

async function handleAnalyzeFile(file: TOEFile, focus: 'st_pp' | 'manual') {
  analyzingFileId.value = file.id
  try {
    // Use async version, return task ID immediately
    const taskRes = await toeApi.aiAnalyzeDocAsync(toeId, file.id, focus, localeStore.lang)
    const taskId = taskRes.data.task_id
    message.loading(t.value.toe.aiTaskStarted)
    
    // Poll task progress
    const result = await pollAnalysisTask(taskId, file.original_filename)
    if (result) {
      pendingAnalysis.value = result as Record<string, string>
      showAnalysisPreview.value = true
      message.success(t.value.toe.aiAnalyzeDocsSuccess)
    }
  } catch (e: any) {
    message.error(e.message)
  } finally {
    analyzingFileId.value = null
  }
}

// Poll async task progress and display detailed progress info
async function pollAnalysisTask(taskId: string, fileName: string, maxWaitSeconds = 600): Promise<Record<string, string> | null> {
  const startTime = Date.now()
  const maxWaitMs = maxWaitSeconds * 1000
  let lastMessage = ''
  
  while (Date.now() - startTime < maxWaitMs) {
    try {
      const res = await fetch(`/api/tasks/${taskId}`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      }).then(r => r.json())
      
      const task = res.data
      
      // Update progress message (avoid duplicate prompts)
      if (task.progress_message && task.progress_message !== lastMessage) {
        lastMessage = task.progress_message
        // Show progress message, e.g.: "Extracting (1/6): TOE Type..."
        message.loading(task.progress_message)
      }
      
      if (task.status === 'done') {
        message.destroyAll()
        if (task.result_summary) {
          return JSON.parse(task.result_summary)
        }
        return null
      }
      
      if (task.status === 'failed') {
        message.destroyAll()
        throw new Error(task.error_message || `${t.value.toe.aiTaskFailed}: ${fileName}`)
      }
      
      // Check every 2 seconds
      await new Promise(resolve => setTimeout(resolve, 2000))
    } catch (e: any) {
      message.destroyAll()
      throw e
    }
  }
  
  message.destroyAll()
  throw new Error(t.value.toe.aiTaskTimeout.replace('{seconds}', String(maxWaitSeconds)))
}

function cancelAnalysis() {
  showAnalysisPreview.value = false
  pendingAnalysis.value = {}
}

async function confirmAnalysis() {
  applyingAnalysis.value = true
  try {
    // Field mapping: Backend extracted fields -> TOE model fields
    const fieldMapping: Record<string, string> = {
      'toe_type': 'toe_type_desc',        // ST/PP extracted "TOE Type" → toe_type_desc
      'toe_description': 'description',  // ST/PP extracted "TOE Description" → description
    }
    
    for (const [field, val] of Object.entries(pendingAnalysis.value)) {
      if (val) {
        // Use mapped field name if available, otherwise use original field name
        const targetField = fieldMapping[field] || field
        editForm.value[targetField] = appendField(editForm.value[targetField], val)
      }
    }
    await toeApi.update(toeId, editForm.value)
    const updated = await toeApi.get(toeId)
    toe.value = updated.data
    editForm.value = { ...updated.data }
    showAnalysisPreview.value = false
    pendingAnalysis.value = {}
    message.success(t.value.toe.aiAnalyzeAppended)
    showEditDrawer.value = true
  } catch (e: any) {
    message.error(e.message)
  } finally {
    applyingAnalysis.value = false
  }
}

// ── AI consolidate overview fields ──
async function handleConsolidate() {
  consolidating.value = true
  try {
    const res = await toeApi.aiConsolidate(toeId, localeStore.lang)
    const d = res.data
    for (const [field, val] of Object.entries(d)) {
      if (val) (editForm.value as any)[field] = val
    }
    await toeApi.update(toeId, editForm.value)
    const updated = await toeApi.get(toeId)
    toe.value = updated.data
    editForm.value = { ...updated.data }
    message.success(t.value.toe.aiConsolidateSuccess)
    showEditDrawer.value = true
  } catch (e: any) {
    message.error(e.message)
  } finally {
    consolidating.value = false
  }
}

async function handleConsolidateField(field: string) {
  if (consolidatingFields.value.includes(field)) {
    return
  }
  
  consolidatingFields.value.push(field)
  try {
    const res = await toeApi.aiConsolidateFields(toeId, [field], localeStore.lang)
    if (res.data[field]) {
      // Show review modal
      consolidateReviewField.value = field
      consolidateReviewContent.value = res.data[field]
      showConsolidateReview.value = true
    } else {
      message.info(t.value.toe.consolidateNoContent)
    }
  } catch (e: any) {
    message.error(e.message)
  } finally {
    consolidatingFields.value = consolidatingFields.value.filter(f => f !== field)
  }
}

// ── Consolidate review actions ──
async function confirmConsolidateReview() {
  if (!consolidateReviewField.value) return
  
  reviewingConsolidate.value = true
  try {
    const field = consolidateReviewField.value
    const content = consolidateReviewContent.value
    
    // Update toe data
    ;(toe.value as Record<string, any>)[field] = content
    editForm.value[field] = content
    
    // Save to database
    await toeApi.update(toeId, { [field]: content })
    message.success(t.value.toe.aiConsolidateSuccess)
    
    // Close review modal
    showConsolidateReview.value = false
    consolidateReviewField.value = null
    consolidateReviewContent.value = ''
  } catch (e: any) {
    message.error(e.message)
  } finally {
    reviewingConsolidate.value = false
  }
}

function cancelConsolidateReview() {
  showConsolidateReview.value = false
  consolidateReviewField.value = null
  consolidateReviewContent.value = ''
}

// ── Asset actions ──
function openAssetDrawer(asset?: TOEAsset) {
  editingAssetId.value = asset?.id || null
  assetForm.value = {
    name: asset?.name || '',
    description: asset?.description || '',
    asset_type: asset?.asset_type || 'data',
    importance: asset?.importance || 3,
    importance_reason: asset?.importance_reason || '',
    asset_ids: asset?.id ? (assetThreatMap.value[asset.id]?.map(t => t.id) || []) : [],
  }
  selectedThreatIds.value = assetForm.value.asset_ids
  showAssetDrawer.value = true
}

function goToThreat(threatId: string) {
  router.push({ name: 'Threats', query: { toeId, tab: 'threats', focusThreatId: threatId } })
}

function handleFocusedAsset() {
  const focusAssetId = typeof route.query.focusAssetId === 'string' ? route.query.focusAssetId : null
  if (!focusAssetId || activeTab.value !== 'assets') {
    return
  }
  const asset = assets.value.find(item => item.id === focusAssetId)
  if (!asset) {
    return
  }
  openAssetDrawer(asset)
  router.replace({ query: { ...route.query, focusAssetId: undefined } })
}

async function saveAsset() {
  try { await assetFormRef.value?.validate() } catch { return }
  assetSaving.value = true
  try {
    assetForm.value.asset_ids = selectedThreatIds.value
    if (editingAssetId.value) {
      await toeApi.updateAsset(toeId, editingAssetId.value, assetForm.value)
    } else {
      await toeApi.createAsset(toeId, assetForm.value)
    }
    message.success(t.value.common.success)
    showAssetDrawer.value = false
    loadAssets()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    assetSaving.value = false
  }
}

function deleteAsset(asset: TOEAsset) {
  dialog.warning({
    title: t.value.toe.deleteConfirm, content: t.value.toe.deleteAssetConfirm,
    positiveText: t.value.common.delete, negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      try { await toeApi.deleteAsset(toeId, asset.id); message.success(t.value.common.success); loadAssets() }
      catch (e: any) { message.error(e.message) }
    },
  })
}

async function batchDeleteAssets() {
  if (selectedAssetIds.value.length === 0) return
  dialog.warning({
    title: t.value.toe.deleteConfirm,
    content: `${t.value.toe.deleteAssetConfirm} (${selectedAssetIds.value.length} ${t.value.toe.assets})`,
    positiveText: t.value.common.delete,
    negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      batchDeleting.value = true
      try {
        for (const assetId of selectedAssetIds.value) {
          await toeApi.deleteAsset(toeId, assetId)
        }
        message.success(t.value.common.success)
        selectedAssetIds.value = []
        loadAssets()
      } catch (e: any) {
        message.error(e.message)
      } finally {
        batchDeleting.value = false
      }
    },
  })
}

async function handleAiSuggest() {
  aiSuggesting.value = true
  try {
    const res = await toeApi.aiSuggestAssets(toeId, localeStore.lang)
    aiSuggestions.value = Array.isArray(res.data) ? res.data : []
    if (!aiSuggestions.value.length) message.info(t.value.toe.noNewSuggestions)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    aiSuggesting.value = false
  }
}

async function acceptSuggestion(s: any) {
  try {
    await toeApi.createAsset(toeId, { ...s, ai_generated: true })
    message.success(t.value.toe.adoptedAsset)
    aiSuggestions.value = aiSuggestions.value.filter(x => x !== s)
    loadAssets()
  } catch (e: any) {
    message.error(e.message)
  }
}

// ── File actions ──
async function handleFileUpload({ file }: { file: any }, category: string) {
  try {
    await toeApi.uploadFile(toeId, file.file, category)
    message.success(t.value.toe.fileUploadSuccess)
    loadFiles()
  } catch (e: any) {
    message.error(e.message)
  }
}

function deleteFile(f: TOEFile) {
  dialog.warning({
    title: t.value.toe.deleteConfirm, content: t.value.toe.deleteFileConfirm,
    positiveText: t.value.common.delete, negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      try { await toeApi.deleteFile(toeId, f.id); message.success(t.value.common.success); loadFiles() }
      catch (e: any) { message.error(e.message) }
    },
  })
}

onMounted(async () => {
  await loadToe()
  loadAssets()
  loadRelatedThreats()
  loadFiles()
})
onUnmounted(() => stopFilePolling())

watch(() => route.query.focusAssetId, () => {
  handleFocusedAsset()
})
</script>

<style scoped>
/* ── Overview grid ── */
.overview-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.overview-section {
  border: 1px solid var(--n-border-color, #e0e0e0);
  border-radius: 8px;
  padding: 14px 16px;
  background: var(--n-color, #fff);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.overview-section.full-width {
  /* no-op, kept for compat */
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-icon {
  font-size: 14px;
  line-height: 1;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.55;
}

.section-body {
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Edit label ── */
.edit-label {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  font-weight: 500;
  flex-wrap: wrap;
}

.edit-label span:first-child {
  flex-shrink: 0;
}
</style>
