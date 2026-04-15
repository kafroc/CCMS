<template>
	<div>
		<n-space justify="space-between" style="margin-bottom: 12px; flex-wrap: wrap" :size="12">
			<n-select
				v-model:value="filterStatus"
				:options="statusOptions"
				:placeholder="t.security.filterStatus"
				clearable
				style="width: 140px"
			/>
			<n-space :size="8" style="flex-wrap: wrap">
				<template v-if="canWrite && checkedRowKeys.length > 0">
					<n-button
						size="small"
						:color="neutralButtonColor"
						text-color="#111827"
						border-color="#d1d5db"
						@click="batchConfirm"
					>
						{{ t.common.confirm }} ({{ checkedRowKeys.length }})
					</n-button>
					<n-button
						size="small"
						:loading="batchDeleting"
						:color="neutralButtonColor"
						text-color="#111827"
						border-color="#d1d5db"
						@click="batchDelete"
					>
						{{ t.common.delete }} ({{ checkedRowKeys.length }})
					</n-button>
				</template>
				<n-dropdown v-if="canWrite" trigger="click" :options="aiDropdownOptions" @select="handleAiSelect">
					<n-button
						size="small"
						:loading="aiLoading"
						:color="neutralButtonColor"
						text-color="#111827"
						border-color="#d1d5db"
					>
						{{ t.security.aiSuggest }}
					</n-button>
				</n-dropdown>
				<n-button
					v-if="canWrite"
					size="small"
					:loading="aiCompletionLoading"
					:color="neutralButtonColor"
					text-color="#111827"
					border-color="#d1d5db"
					@click="handleAiCompletionEntry"
				>
					{{ t.security.aiCompleteSfr }}
				</n-button>
				<n-button
					v-if="canWrite"
					size="small"
					:color="neutralButtonColor"
					text-color="#111827"
					border-color="#d1d5db"
					@click="openAdd"
				>
					+ {{ t.security.addSfr }}
				</n-button>
			</n-space>
		</n-space>

		<n-data-table
			:columns="columns"
			:data="filteredSFRs"
			:loading="loading"
			:row-key="(row: SFRInstance) => row.id"
			v-model:checked-row-keys="checkedRowKeys"
			size="small"
		/>

		<n-drawer v-model:show="drawerVisible" :width="620" placement="right">
			<n-drawer-content :title="editItem ? `${t.security.editSfr} ${editItem.sfr_id}` : t.security.addSfr" closable>
				<n-form :model="editForm" label-placement="top" size="small" :disabled="!canWrite">
					<n-form-item :label="t.security.sfrId" required>
						<n-input v-model:value="editForm.sfr_id" placeholder="FDP_ACC.1" />
					</n-form-item>
					<n-space v-if="canWrite" justify="end" style="margin: -6px 0 12px">
						<n-button
							size="small"
							:loading="aiCompletionLoading"
							:color="neutralButtonColor"
							text-color="#111827"
							border-color="#d1d5db"
							@click="runAiCompletion"
						>
							{{ t.security.aiCompleteSfr }}
						</n-button>
					</n-space>
					<n-form-item :label="t.security.sfrName">
						<n-input v-model:value="editForm.sfr_name" />
					</n-form-item>
					<n-form-item :label="t.security.sfrDetail">
						<n-input v-model:value="editForm.sfr_detail" type="textarea" :rows="5" />
					</n-form-item>
					<n-form-item :label="t.security.dependencies">
						<n-input v-model:value="editForm.dependency" />
					</n-form-item>
					<n-form-item :label="t.security.linkedObjectives">
						<n-select
							v-model:value="editForm.objective_ids"
							:options="objectiveOptions"
							multiple
							clearable
							filterable
							:placeholder="t.security.selectObjectives"
						/>
					</n-form-item>
					<n-form-item :label="t.test.linkedTests">
						<n-select
							v-model:value="editForm.linked_test_ids"
							:options="testOptions"
							multiple
							clearable
							filterable
							:placeholder="t.security.selectTests"
						/>
					</n-form-item>
				</n-form>
				<n-divider />
				<n-space justify="end">
					<n-button
						v-if="editItem && canWrite"
						:color="neutralButtonColor"
						text-color="#111827"
						border-color="#d1d5db"
						@click="handleDeleteFromDrawer"
					>
						{{ t.common.delete }}
					</n-button>
					<n-button @click="drawerVisible = false">{{ t.common.cancel }}</n-button>
					<n-button
						v-if="canWrite"
						:loading="saveLoading"
						:color="neutralButtonColor"
						text-color="#111827"
						border-color="#d1d5db"
						@click="saveItem"
					>
						{{ t.common.save }}
					</n-button>
				</n-space>
			</n-drawer-content>
		</n-drawer>

		<n-modal v-model:show="aiSuggestionModalVisible" :mask-closable="false" preset="card" :title="t.security.aiCompleteSfr" style="width: 560px">
			<n-space vertical :size="16">
				<div v-if="!suggestionObjectiveOptions.length && !suggestionTestOptions.length" style="color: #666">
					{{ t.security.aiCompletionNoSuggestions }}
				</div>
				<template v-else>
					<div>
						<div style="font-weight: 600; margin-bottom: 8px">{{ t.security.linkedObjectives }}</div>
						<n-checkbox-group v-model:value="aiSuggestionSelection.objective_ids">
							<n-space vertical>
								<n-checkbox v-for="item in suggestionObjectiveOptions" :key="item.value" :value="item.value">
									{{ item.label }}
								</n-checkbox>
							</n-space>
						</n-checkbox-group>
					</div>
					<div>
						<div style="font-weight: 600; margin-bottom: 8px">{{ t.test.linkedTests }}</div>
						<n-checkbox-group v-model:value="aiSuggestionSelection.test_ids">
							<n-space vertical>
								<n-checkbox v-for="item in suggestionTestOptions" :key="item.value" :value="item.value">
									{{ item.label }}
								</n-checkbox>
							</n-space>
						</n-checkbox-group>
					</div>
				</template>
			</n-space>
			<template #footer>
				<n-space justify="end">
					<n-button @click="aiSuggestionModalVisible = false">{{ t.common.cancel }}</n-button>
					<n-button
						v-if="canWrite"
						:color="neutralButtonColor"
						text-color="#111827"
						border-color="#d1d5db"
						@click="applyAiSuggestions"
					>
						{{ t.common.confirm }}
					</n-button>
				</n-space>
			</template>
		</n-modal>

		<n-modal v-model:show="aiModalVisible" :mask-closable="false" preset="card" :title="t.security.aiSuggest" style="width: 440px">
			<div style="text-align: center; padding: 16px 0">
				<n-progress type="line" :percentage="aiProgress" :indicator-placement="'inside'" style="margin-bottom: 16px" />
				<p style="color: #666; font-size: 13px">{{ aiStatusMsg }}</p>
			</div>
			<template #footer>
				<n-button :disabled="aiProgress < 100 && !aiFailed" @click="closeAiModal">
					{{ aiProgress >= 100 || aiFailed ? t.threat.complete : t.threat.runInBackground }}
				</n-button>
			</template>
		</n-modal>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, h, onUnmounted, watch, nextTick, type ComputedRef } from 'vue'
import { useMessage, NButton, NSpace } from 'naive-ui'
import { useRouter } from 'vue-router'
import { securityApi } from '@/api/security'
import { testApi, type TestCase } from '@/api/tests'
import { taskApi } from '@/api/tasks'
import type { SecurityObjective, SFRInstance } from '@/api/security'
import type { DataTableColumns, DataTableRowKey } from 'naive-ui'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))

const props = defineProps<{
	toeId: string
	objectives: SecurityObjective[]
	sfrs: SFRInstance[]
	loading: boolean
	canWrite: boolean
}>()

const emit = defineEmits<{ (e: 'refresh'): void }>()
const message = useMessage()
const router = useRouter()

const neutralButtonColor = '#f3f4f6'
const neutralBorderColor = '#d1d5db'
const neutralTextColor = '#111827'
const canWrite = computed(() => props.canWrite)

const filterStatus = ref<string | null>(null)
const statusOptions = computed(() => [
	{ label: t.value.security.draft, value: 'draft' },
	{ label: t.value.security.confirmed, value: 'confirmed' },
	{ label: t.value.security.rejected, value: 'rejected' },
])

const filteredSFRs = computed(() => {
	if (!filterStatus.value) return props.sfrs
	return props.sfrs.filter(item => item.review_status === filterStatus.value)
})

const objectiveOptions = computed(() => props.objectives.map(item => ({
	label: `${item.code} (${item.obj_type})`,
	value: item.id,
})))

const testCases = ref<TestCase[]>([])
const testOptions = computed(() => testCases.value.map(item => ({ label: item.case_number || item.id.substring(0, 8).toUpperCase(), value: item.id })))

async function loadTests() {
	if (!props.toeId) return
	try {
		const res = await testApi.list(props.toeId)
		testCases.value = res.data
	} catch (e: any) {
		message.error(e.message)
	}
}

function goToObjective(id: string) {
	router.push({ name: 'Security', query: { toeId: props.toeId, tab: 'objectives', focusObjectiveId: id } })
}

function goToTest(id: string) {
	router.push({ name: 'Tests', query: { toeId: props.toeId, tab: 'list', focusTestId: id } })
}

function goToSfr(id: string) {
	const target = props.sfrs.find(item => item.id === id)
	if (target) {
		openEdit(target)
	}
}

function wrapCellText(value: string) {
	return h('div', {
		style: {
			whiteSpace: 'normal',
			wordBreak: 'break-word',
			lineHeight: '1.5',
			padding: '6px 0',
		},
	}, value)
}

function isFillingDependencies(sfrId: string) {
	return fillingDependencyIds.value.includes(sfrId)
}

async function fillDependencies(row: SFRInstance) {
	if (!row.dependency_warning) {
		message.info(t.value.security.noMissingDependencies)
		return
	}
	fillingDependencyIds.value = [...fillingDependencyIds.value, row.id]
	try {
		const res = await securityApi.fillSFRDependencies(props.toeId, row.id)
		message.success(
			t.value.security.fillDependenciesDone
				.replace('{count}', String(res.data.created_count))
				.replace('{mappings}', String(res.data.linked_objective_mappings))
		)
		emit('refresh')
	} catch (e: any) {
		message.error(e.message)
	} finally {
		fillingDependencyIds.value = fillingDependencyIds.value.filter(id => id !== row.id)
	}
}

async function syncSfrObjectives(sfrId: string, nextObjectiveIds: string[], currentObjectiveIds: string[]) {
	const toAdd = nextObjectiveIds.filter(id => !currentObjectiveIds.includes(id))
	const toRemove = currentObjectiveIds.filter(id => !nextObjectiveIds.includes(id))

	await Promise.all(toAdd.map(objectiveId => securityApi.addObjectiveSFR(props.toeId, objectiveId, sfrId)))
	await Promise.all(toRemove.map(objectiveId => securityApi.removeObjectiveSFR(props.toeId, objectiveId, sfrId)))
}

type SFRCols = DataTableColumns<SFRInstance>
const columns: ComputedRef<SFRCols> = computed(() => [
	...(canWrite.value ? [{ type: 'selection' as const, width: 32, minWidth: 24, resizable: true }] : []),
	{ title: t.value.security.sfrId, key: 'sfr_id', width: 90, minWidth: 60, resizable: true, render: row => wrapCellText(row.sfr_id) },
	{
		title: t.value.security.sfrName,
		key: 'sfr_name',
		width: 140,
		minWidth: 80,
		resizable: true,
		render: row => wrapCellText(row.sfr_name ?? row.library?.sfr_component_name ?? '-'),
	},
	{
		title: t.value.security.sfrDetail,
		key: 'sfr_detail',
		width: 520,
		minWidth: 180,
		resizable: true,
		render: row => wrapCellText(row.sfr_detail ?? row.library?.description ?? '-'),
	},
	{
		title: t.value.security.dependencies,
		key: 'dependency',
		width: 180,
		minWidth: 100,
		resizable: true,
		render: row => {
			const dependencyText = row.dependency ?? row.library?.dependencies ?? '-'
			const children = [wrapCellText(dependencyText)]
			if (row.dependency_warning) {
				children.push(h('div', {
					style: {
						fontSize: '12px',
						lineHeight: '1.5',
						color: '#b45309',
						marginTop: '4px',
					}
				}, row.dependency_warning))
				if (canWrite.value) {
					children.push(h(NButton, {
						size: 'tiny',
						style: { marginTop: '6px' },
						color: '#fef3c7',
						textColor: '#92400e',
						borderColor: '#f59e0b',
						loading: isFillingDependencies(row.id),
						onClick: () => fillDependencies(row),
					}, () => t.value.security.fillDependencies))
				}
			}
			return h('div', children)
		},
	},
	{
		title: t.value.security.linkedObjSfr,
		key: 'linked_obj_sfr',
		width: 220,
		minWidth: 110,
		resizable: true,
		render: row => {
			const linkedObjectives = row.linked_objectives ?? []
			const linkedDependencySfrs = row.linked_dependency_sfrs ?? []
			const chips = [
				...linkedObjectives.map(objective =>
					h(NButton, {
						size: 'tiny',
						color: neutralButtonColor,
						textColor: neutralTextColor,
						borderColor: neutralBorderColor,
						onClick: () => goToObjective(objective.id),
					}, () => `${objective.code} (${objective.obj_type})`)
				),
				...linkedDependencySfrs.map(sfr =>
					h(NButton, {
						size: 'tiny',
						color: '#eef2ff',
						textColor: '#1f2937',
						borderColor: '#c7d2fe',
						onClick: () => goToSfr(sfr.id),
					}, () => sfr.sfr_id)
				),
			]
			if (!chips.length) return h('span', { style: 'color:#999' }, '-')
			return h(NSpace, { size: 'small', wrap: true }, () => chips)
		},
	},
	{
		title: t.value.test.linkedTests,
		key: 'linked_tests',
		width: 130,
		minWidth: 72,
		resizable: true,
		render: row => {
			const linkedTests = row.linked_tests ?? []
			if (!linkedTests.length) return h('span', { style: 'color:#999' }, '-')
			const unique = linkedTests.filter((tc, idx, arr) => arr.findIndex(x => x.id === tc.id) === idx)
			return h(NSpace, { size: 'small', wrap: true }, () => unique.map(testCase =>
				h(NButton, {
					size: 'tiny',
					color: neutralButtonColor,
					textColor: neutralTextColor,
					borderColor: neutralBorderColor,
					onClick: () => goToTest(testCase.id),
				}, () => testCase.case_number || testCase.id.substring(0, 8).toUpperCase())
			))
		},
	},
	{
		title: t.value.toe.operation,
		key: 'actions',
		width: 72,
		minWidth: 56,
		resizable: true,
		render: row => h(NButton, {
			size: 'tiny',
			color: neutralButtonColor,
			textColor: neutralTextColor,
			borderColor: neutralBorderColor,
			onClick: () => openEdit(row),
		}, () => t.value.common.edit),
	},
])

const drawerVisible = ref(false)
const editItem = ref<SFRInstance | null>(null)
const saveLoading = ref(false)
const editForm = ref({
	sfr_id: '',
	sfr_name: '',
	sfr_detail: '',
	dependency: '',
	source: 'manual',
	objective_ids: [] as string[],
	linked_test_ids: [] as string[],
})

const checkedRowKeys = ref<DataTableRowKey[]>([])
const batchDeleting = ref(false)
const aiCompletionLoading = ref(false)
const fillingDependencyIds = ref<string[]>([])
const aiSuggestionModalVisible = ref(false)
const aiSuggestionSelection = ref({ objective_ids: [] as string[], test_ids: [] as string[] })
const suggestionObjectiveOptions = ref<Array<{ label: string; value: string }>>([])
const suggestionTestOptions = ref<Array<{ label: string; value: string }>>([])

function openAdd() {
	editItem.value = null
	editForm.value = {
		sfr_id: '',
		sfr_name: '',
		sfr_detail: '',
		dependency: '',
		source: 'manual',
		objective_ids: [],
		linked_test_ids: [],
	}
	drawerVisible.value = true
}

function openEdit(item: SFRInstance) {
	editItem.value = item
	editForm.value = {
		sfr_id: item.sfr_id,
		sfr_name: item.sfr_name ?? item.library?.sfr_component_name ?? '',
		sfr_detail: item.sfr_detail ?? item.library?.description ?? '',
		dependency: item.dependency ?? item.library?.dependencies ?? '',
		source: item.source ?? 'manual',
		objective_ids: [...(item.objective_ids ?? [])],
		linked_test_ids: [...new Set((item.linked_tests ?? []).map(testCase => testCase.id))],
	}
	drawerVisible.value = true
}

async function handleDeleteFromDrawer() {
	if (!editItem.value) return
	await deleteItem(editItem.value)
	drawerVisible.value = false
	editItem.value = null
}

function parseRelatedIds(value: string | null) {
	if (!value) return [] as string[]
	try {
		const parsed = JSON.parse(value)
		return Array.isArray(parsed) ? parsed.filter(item => typeof item === 'string') : []
	} catch {
		return []
	}
}

function toRelatedIdsValue(ids: string[]) {
	return JSON.stringify(ids)
}

async function syncSfrTests(sfrDbId: string, nextTestIds: string[], currentTestIds: string[]) {
	for (const testCase of testCases.value) {
		const wasLinked = currentTestIds.includes(testCase.id)
		const willLinked = nextTestIds.includes(testCase.id)
		if (wasLinked === willLinked) continue

		const relatedIds = parseRelatedIds(testCase.related_sfr_ids)
		if (willLinked) {
			if (relatedIds.includes(sfrDbId)) continue
			await testApi.update(props.toeId, testCase.id, {
				related_sfr_ids: toRelatedIdsValue([...relatedIds, sfrDbId]),
			})
			continue
		}

		if (testCase.primary_sfr_id === sfrDbId) {
			const alternatives = relatedIds.filter(id => id !== sfrDbId)
			if (!alternatives.length) {
				// Only link is via primary; clear related_sfr_ids to unlink
				await testApi.update(props.toeId, testCase.id, {
					related_sfr_ids: toRelatedIdsValue([]),
				})
				continue
			}
			const [nextPrimary, ...nextRelated] = alternatives
			await testApi.update(props.toeId, testCase.id, {
				primary_sfr_id: nextPrimary,
				related_sfr_ids: toRelatedIdsValue(nextRelated),
			})
			continue
		}

		await testApi.update(props.toeId, testCase.id, {
			related_sfr_ids: toRelatedIdsValue(relatedIds.filter(id => id !== sfrDbId)),
		})
	}
}

async function saveItem() {
	if (!editForm.value.sfr_id.trim()) {
		message.warning(t.value.security.sfrIdRequired)
		return
	}
	saveLoading.value = true
	try {
		if (editItem.value) {
			await securityApi.updateSFR(props.toeId, editItem.value.id, editForm.value)
			await syncSfrObjectives(editItem.value.id, editForm.value.objective_ids, editItem.value.objective_ids ?? [])
			await syncSfrTests(editItem.value.id, editForm.value.linked_test_ids, (editItem.value.linked_tests ?? []).map(testCase => testCase.id))
		} else {
			const res = await securityApi.createSFR(props.toeId, editForm.value)
			await syncSfrObjectives(res.data.id, editForm.value.objective_ids, [])
			await syncSfrTests(res.data.id, editForm.value.linked_test_ids, [])
		}
		message.success(t.value.common.success)
		drawerVisible.value = false
		await loadTests()
		emit('refresh')
	} catch (e: any) {
		message.error(e.message)
	} finally {
		saveLoading.value = false
	}
}

async function deleteItem(item: SFRInstance) {
	try {
		await securityApi.deleteSFR(props.toeId, item.id)
		message.success(t.value.common.success)
		await loadTests()
		emit('refresh')
	} catch (e: any) {
		message.error(e.message)
	}
}

async function batchConfirm() {
	try {
		for (const id of checkedRowKeys.value) {
			await securityApi.confirmSFR(props.toeId, id as string)
		}
		message.success(`${t.value.security.confirmed} ${checkedRowKeys.value.length}`)
		checkedRowKeys.value = []
		emit('refresh')
	} catch (e: any) {
		message.error(e.message)
	}
}

async function batchDelete() {
	batchDeleting.value = true
	try {
		for (const id of checkedRowKeys.value) {
			await securityApi.deleteSFR(props.toeId, id as string)
		}
		message.success(`${t.value.common.delete} ${checkedRowKeys.value.length}`)
		checkedRowKeys.value = []
		await loadTests()
		emit('refresh')
	} catch (e: any) {
		message.error(e.message)
	} finally {
		batchDeleting.value = false
	}
}

const aiDropdownOptions = computed(() => [
	{ label: t.value.security.fullMatch, key: 'full' },
	{ label: t.value.security.incrementalMatch, key: 'incremental' },
	{ label: t.value.security.stPpValidate, key: 'st_pp' },
])

const aiLoading = ref(false)
const aiModalVisible = ref(false)
const aiProgress = ref(0)
const aiStatusMsg = ref(t.value.threat.initTask)
const aiFailed = ref(false)
const aiTaskId = ref<string | null>(null)
let aiTimer: ReturnType<typeof setInterval> | null = null

function parseAiProgress(progressMessage?: string | null) {
	if (!progressMessage) return null
	const objectiveMatch = progressMessage.match(/(?:Matching|Validating) security objectives\s+(\d+)\/(\d+)/)
	if (objectiveMatch) {
		const current = Number(objectiveMatch[1])
		const total = Number(objectiveMatch[2])
		if (total > 0) {
			return Math.min(100, Math.max(0, Math.round((current / total) * 100)))
		}
	}
	if (progressMessage.includes('Phase 1/5')) return 5
	if (progressMessage.includes('Phase 2/5')) return 10
	if (progressMessage.includes('Phase 3/5')) return 15
	if (progressMessage.includes('Phase 4/5')) return 20
	if (progressMessage.includes('Phase 5/5')) return 95
	return null
}

async function handleAiCompletionEntry() {
	if (!props.toeId) return
	if (drawerVisible.value) {
		await runAiCompletion()
		return
	}
	if (checkedRowKeys.value.length !== 1) {
		await runAutoManage()
		return
	}
	const target = props.sfrs.find(item => item.id === checkedRowKeys.value[0])
	if (!target) return
	openEdit(target)
	await nextTick()
	await runAiCompletion()
}

async function runAutoManage() {
	const res = await securityApi.autoManageSFRs(props.toeId)
	message.success(res.data.updated > 0 ? t.value.common.success : t.value.threat.actionNoGaps)
	await loadTests()
	emit('refresh')
}

async function runAiCompletion() {
	if (!editForm.value.sfr_id.trim()) {
		message.warning(t.value.security.sfrIdRequired)
		return
	}
	aiCompletionLoading.value = true
	try {
		const res = await securityApi.aiCompleteSFR(props.toeId, {
			sfr_id: editForm.value.sfr_id,
			current_objective_ids: editForm.value.objective_ids,
			current_test_ids: editForm.value.linked_test_ids,
		})
		const data = res.data
		editForm.value.sfr_name = data.sfr_name ?? editForm.value.sfr_name
		editForm.value.sfr_detail = data.sfr_detail ?? editForm.value.sfr_detail
		editForm.value.dependency = data.dependency ?? editForm.value.dependency

		suggestionObjectiveOptions.value = data.available_objectives
			.map(item => ({ label: `${item.code} (${item.obj_type})`, value: item.id }))
			.filter(item => data.suggested_objective_ids.includes(item.value))
		suggestionTestOptions.value = data.available_tests
			.map(item => ({ label: item.title, value: item.id }))
			.filter(item => data.suggested_test_ids.includes(item.value))
		aiSuggestionSelection.value = {
			objective_ids: Array.from(new Set([...editForm.value.objective_ids, ...data.suggested_objective_ids])),
			test_ids: Array.from(new Set([...editForm.value.linked_test_ids, ...data.suggested_test_ids])),
		}
		if (suggestionObjectiveOptions.value.length || suggestionTestOptions.value.length) {
			aiSuggestionModalVisible.value = true
		} else {
			message.success(t.value.security.aiCompletionApplied)
		}
		await runAutoManage()
	} catch (e: any) {
		message.error(e.message)
	} finally {
		aiCompletionLoading.value = false
	}
}

function applyAiSuggestions() {
	editForm.value.objective_ids = [...aiSuggestionSelection.value.objective_ids]
	editForm.value.linked_test_ids = [...aiSuggestionSelection.value.test_ids]
	aiSuggestionModalVisible.value = false
	message.success(t.value.security.aiCompletionApplied)
}

async function handleAiSelect(key: string) {
	aiModalVisible.value = true
	aiProgress.value = 0
	aiStatusMsg.value = t.value.threat.initTask
	aiFailed.value = false
	aiLoading.value = true
	try {
		const res = key === 'st_pp'
			? await securityApi.stppValidateSFRs(props.toeId, localeStore.lang)
			: await securityApi.aiMatchSFRs(props.toeId, key, localeStore.lang)
		aiTaskId.value = res.data.task_id
		aiTimer = setInterval(async () => {
			if (!aiTaskId.value) return
			try {
				const task = (await taskApi.get(aiTaskId.value)).data
				if (task.status === 'done') {
					aiProgress.value = 100
					aiStatusMsg.value = task.result_summary ?? t.value.threat.scanComplete
					clearInterval(aiTimer!)
					aiTimer = null
					emit('refresh')
				} else if (task.status === 'failed') {
					aiProgress.value = 0
					aiStatusMsg.value = `${t.value.threat.scanFailed}: ${task.error_message ?? t.value.common.error}`
					aiFailed.value = true
					clearInterval(aiTimer!)
					aiTimer = null
				} else {
					const nextProgress = parseAiProgress(task.progress_message)
					aiProgress.value = nextProgress ?? aiProgress.value
					aiStatusMsg.value = task.progress_message ?? t.value.threat.processing
				}
			} catch (_) {}
		}, 2000)
	} catch (e: any) {
		aiStatusMsg.value = `${t.value.threat.submitFailed}: ${e.message}`
		aiFailed.value = true
	} finally {
		aiLoading.value = false
	}
}

function closeAiModal() {
	if (aiTimer) {
		clearInterval(aiTimer)
		aiTimer = null
	}
	aiModalVisible.value = false
}

watch(() => props.toeId, () => {
	checkedRowKeys.value = []
	loadTests()
}, { immediate: true })

onUnmounted(() => {
	if (aiTimer) clearInterval(aiTimer)
})
</script>