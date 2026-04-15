<template>
  <div>
    <n-page-header :title="t.user.title" subtitle="">
      <template #extra>
        <n-button type="primary" @click="openCreate">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          {{ t.user.addUser }}
        </n-button>
      </template>
    </n-page-header>

    <n-card style="margin-top: 16px">
      <n-data-table
        :columns="columns"
        :data="users"
        :loading="loading"
        :row-key="(row: User) => row.id"
      />
    </n-card>

    <!-- Create user dialog -->
    <n-modal v-model:show="showCreate" preset="card" :title="t.user.addUser" style="width: 440px">
      <n-form ref="createFormRef" :model="createForm" :rules="createRules" label-placement="left" label-width="80">
        <n-form-item :label="t.user.username" path="username">
          <n-input v-model:value="createForm.username" :placeholder="t.user.username" />
        </n-form-item>
        <n-form-item :label="t.user.password" path="password">
          <n-input v-model:value="createForm.password" type="password" :placeholder="t.user.password" show-password-on="click" />
        </n-form-item>
        <n-form-item :label="t.user.role" path="role">
          <n-select v-model:value="createForm.role" :options="roleOptions" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreate = false">{{ t.common.cancel }}</n-button>
          <n-button type="primary" :loading="submitting" @click="handleCreate">{{ t.common.create }}</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Change password dialog -->
    <n-modal v-model:show="showChangePwd" preset="card" :title="t.user.changePassword" style="width: 440px">
      <n-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-placement="left" label-width="80">
        <n-form-item :label="t.user.oldPassword" path="old_password">
          <n-input v-model:value="pwdForm.old_password" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item :label="t.user.newPassword" path="new_password">
          <n-input v-model:value="pwdForm.new_password" type="password" show-password-on="click" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showChangePwd = false">{{ t.common.cancel }}</n-button>
          <n-button type="primary" :loading="submitting" @click="handleChangePwd">{{ t.common.confirm }}</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="showToeAccess" preset="card" :title="t.user.manageToeAccess" style="width: 640px">
      <n-space vertical :size="16">
        <n-select
          v-model:value="selectedToeIds"
          multiple
          filterable
          clearable
          :options="toeOptions"
          :placeholder="t.user.selectToeAccess"
          @update:value="handleToeSelectionChange"
        />
        <n-space vertical :size="12">
          <div v-for="item in toePermissionForm" :key="item.toe_id" style="display: flex; gap: 12px; align-items: center">
            <div style="flex: 1; min-width: 0">{{ toeNameMap[item.toe_id] || item.toe_id }}</div>
            <n-select v-model:value="item.access_level" :options="accessLevelOptions" style="width: 160px" />
          </div>
        </n-space>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showToeAccess = false">{{ t.common.cancel }}</n-button>
          <n-button type="primary" :loading="submitting" @click="handleSaveToeAccess">{{ t.common.save }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, type ComputedRef } from 'vue'
import { NButton, NSpace, NTag, NIcon, useMessage, useDialog, type FormInst, type FormRules, type DataTableColumns } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { userApi, type User } from '@/api/users'
import { toeApi, type TOE } from '@/api/toes'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

const localeStore = useLocaleStore()
const t = computed(() => getMessages(localeStore.lang))
const message = useMessage()
const dialog = useDialog()

const users = ref<User[]>([])
const loading = ref(false)
const showCreate = ref(false)
const showChangePwd = ref(false)
const showToeAccess = ref(false)
const submitting = ref(false)
const currentUserId = ref('')
const currentPermissionUserId = ref('')
const toes = ref<TOE[]>([])
const toePermissionForm = ref<Array<{ toe_id: string; access_level: string }>>([])
const selectedToeIds = ref<string[]>([])

const createFormRef = ref<FormInst | null>(null)
const pwdFormRef = ref<FormInst | null>(null)

const createForm = ref({ username: '', password: '', role: 'user' })
const pwdForm = ref({ old_password: '', new_password: '' })

const roleOptions = computed(() => [
  { label: t.value.user.normalUser, value: 'user' },
  { label: t.value.user.admin, value: 'admin' },
])
const accessLevelOptions = computed(() => [
  { label: t.value.user.toeReadOnly, value: 'read' },
  { label: t.value.user.toeReadWrite, value: 'write' },
])
const toeOptions = computed(() => toes.value.map(item => ({ label: item.name, value: item.id })))
const toeNameMap = computed(() => Object.fromEntries(toes.value.map(item => [item.id, item.name])))

const createRules: ComputedRef<FormRules> = computed(() => ({
  username: [
    { required: true, message: t.value.user.username },
    { pattern: /^[a-zA-Z0-9]+$/, message: t.value.user.usernameRule },
  ],
  password: [
    { required: true, message: t.value.user.password },
    { min: 6, message: t.value.user.passwordMin },
  ],
}))

const pwdRules: ComputedRef<FormRules> = computed(() => ({
  old_password: [{ required: true, message: t.value.user.password }],
  new_password: [{ required: true, message: t.value.user.password }, { min: 6, message: t.value.user.passwordMin }],
}))

type UserCols = DataTableColumns<User>
const columns: ComputedRef<UserCols> = computed(() => [
  { title: t.value.user.username, key: 'username' },
  {
    title: t.value.user.role,
    key: 'role',
    render: (row) =>
      h(NTag, { type: row.role === 'admin' ? 'primary' : 'default', size: 'small' }, { default: () => row.role === 'admin' ? t.value.user.admin : t.value.user.normalUser }),
  },
  { title: t.value.common.createdAt, key: 'created_at', render: (row) => new Date(row.created_at).toLocaleString() },
  {
    title: t.value.user.toeAccess,
    key: 'toe_permissions',
    render: (row) => {
      if (row.role === 'admin') {
        return h(NTag, { type: 'primary', size: 'small' }, { default: () => t.value.user.allToes })
      }
      if (!row.toe_permissions?.length) {
        return h('span', { style: 'color:#999' }, '-')
      }
      return h(NSpace, { size: 'small', wrap: true }, {
        default: () => row.toe_permissions.map(permission =>
          h(NTag, { size: 'small', type: permission.access_level === 'write' ? 'success' : 'default' }, {
            default: () => `${permission.toe_name} · ${permission.access_level === 'write' ? t.value.user.toeReadWrite : t.value.user.toeReadOnly}`,
          })
        ),
      })
    },
  },
  {
    title: t.value.common.actions,
    key: 'actions',
    render: (row) =>
      h(NSpace, {}, {
        default: () => [
          ...(row.role === 'admin' ? [] : [h(NButton, { size: 'small', onClick: () => openToeAccess(row) }, { default: () => t.value.user.manageToeAccess })]),
          h(NButton, { size: 'small', onClick: () => openChangePwd(row.id) }, { default: () => t.value.user.changePassword }),
          h(NButton, { size: 'small', type: 'error', onClick: () => handleDelete(row) }, { default: () => t.value.common.delete }),
        ],
      }),
  },
])

async function loadUsers() {
  loading.value = true
  try {
    const res = await userApi.list()
    users.value = res.data
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadToes() {
  try {
    const res = await toeApi.list()
    toes.value = res.data
  } catch (e: any) {
    message.error(e.message)
  }
}

function openCreate() {
  createForm.value = { username: '', password: '', role: 'user' }
  showCreate.value = true
}

async function handleCreate() {
  try {
    await createFormRef.value?.validate()
  } catch { return }
  submitting.value = true
  try {
    await userApi.create(createForm.value)
    message.success(t.value.common.success)
    showCreate.value = false
    loadUsers()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    submitting.value = false
  }
}

function openChangePwd(userId: string) {
  currentUserId.value = userId
  pwdForm.value = { old_password: '', new_password: '' }
  showChangePwd.value = true
}

function openToeAccess(user: User) {
  currentPermissionUserId.value = user.id
  toePermissionForm.value = [...(user.toe_permissions || [])].map(item => ({ toe_id: item.toe_id, access_level: item.access_level }))
  selectedToeIds.value = toePermissionForm.value.map(item => item.toe_id)
  showToeAccess.value = true
}

function handleToeSelectionChange(values: string[]) {
  const existing = new Map(toePermissionForm.value.map(item => [item.toe_id, item.access_level]))
  toePermissionForm.value = values.map(toeId => ({ toe_id: toeId, access_level: existing.get(toeId) || 'read' }))
}

async function handleSaveToeAccess() {
  submitting.value = true
  try {
    await userApi.updateToePermissions(currentPermissionUserId.value, toePermissionForm.value)
    message.success(t.value.common.success)
    showToeAccess.value = false
    await Promise.all([loadUsers(), loadToes()])
  } catch (e: any) {
    message.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function handleChangePwd() {
  try {
    await pwdFormRef.value?.validate()
  } catch { return }
  submitting.value = true
  try {
    await userApi.changePassword(currentUserId.value, pwdForm.value)
    message.success(t.value.common.success)
    showChangePwd.value = false
  } catch (e: any) {
    message.error(e.message)
  } finally {
    submitting.value = false
  }
}

function handleDelete(user: User) {
  dialog.warning({
    title: t.value.common.confirmDelete,
    content: `${t.value.common.delete} "${user.username}"?`,
    positiveText: t.value.common.confirm,
    negativeText: t.value.common.cancel,
    onPositiveClick: async () => {
      try {
        await userApi.delete(user.id)
        message.success(t.value.common.success)
        loadUsers()
      } catch (e: any) {
        message.error(e.message)
      }
    },
  })
}

onMounted(() => {
  loadUsers()
  loadToes()
})
</script>