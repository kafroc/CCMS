<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">🛡</div>
        <h1 class="login-title">{{ t.login.title }}</h1>
        <p class="login-subtitle">{{ t.login.subtitle }}</p>
      </div>

      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        @keydown.enter="handleLogin"
      >
        <n-form-item path="username" :label="t.login.username">
          <n-input
            v-model:value="form.username"
            :placeholder="t.login.username"
            :disabled="loading"
            autofocus
          >
            <template #prefix>
              <n-icon><PersonOutline /></n-icon>
            </template>
          </n-input>
        </n-form-item>

        <n-form-item path="password" :label="t.login.password">
          <n-input
            v-model:value="form.password"
            type="password"
            :placeholder="t.login.password"
            show-password-on="click"
            :disabled="loading"
          >
            <template #prefix>
              <n-icon><LockClosedOutline /></n-icon>
            </template>
          </n-input>
        </n-form-item>

        <n-button
          type="primary"
          block
          :loading="loading"
          style="margin-top: 8px; height: 42px; font-size: 15px"
          @click="handleLogin"
        >
          {{ t.login.loginBtn }}
        </n-button>
      </n-form>
    </div>

    <!-- Force password change modal -->
    <n-modal
      v-model:show="showChangePwd"
      :mask-closable="false"
      :close-on-esc="false"
      preset="card"
      :title="t.login.mustChangePwdTitle ?? 'Change your password'"
      style="width: 420px"
    >
      <p style="margin: 0 0 16px 0; color: #666; font-size: 13px">
        {{ t.login.mustChangePwdDesc ?? 'Your account was created with a temporary password. Please set a new one before continuing.' }}
      </p>
      <p style="margin: 0 0 12px 0; color: #999; font-size: 12px; line-height: 1.6">
        {{ t.login.mustChangePwdRules ?? 'Password requirements: at least 10 characters, including uppercase, lowercase, digit, and one special character (!@#$%^&*-_+=?)' }}
      </p>
      <n-form :model="pwdForm" label-placement="top">
        <n-form-item :label="t.login.password">
          <n-input
            v-model:value="pwdForm.new_password"
            type="password"
            show-password-on="click"
            :placeholder="t.login.mustChangePwdNew ?? 'New password (min 6 chars)'"
          />
        </n-form-item>
        <n-form-item :label="t.login.mustChangePwdConfirm ?? 'Confirm password'">
          <n-input
            v-model:value="pwdForm.confirm"
            type="password"
            show-password-on="click"
            :placeholder="t.login.mustChangePwdConfirm ?? 'Confirm password'"
          />
        </n-form-item>
        <n-button type="primary" block :loading="pwdLoading" @click="handleChangePassword">
          {{ t.common.save }}
        </n-button>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { NModal, useMessage, type FormInst, type FormRules } from 'naive-ui'
import { PersonOutline, LockClosedOutline } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'
import { userApi } from '@/api/users'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()
const localeStore = useLocaleStore()

const t = computed(() => getMessages(localeStore.lang))

const formRef = ref<FormInst | null>(null)
const loading = ref(false)

const form = ref({ username: '', password: '' })

const rules: ComputedRef<FormRules> = computed(() => ({
  username: [{ required: true, message: t.value.login.username, trigger: 'blur' }],
  password: [{ required: true, message: t.value.login.password, trigger: 'blur' }],
}))

const showChangePwd = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ new_password: '', confirm: '' })
const tempOldPassword = ref('')

async function handleLogin() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await authStore.login(form.value.username, form.value.password)
    if (authStore.mustChangePassword) {
      tempOldPassword.value = form.value.password
      showChangePwd.value = true
      return
    }
    message.success(t.value.login.loginSuccess)
    router.push('/')
  } catch (e: any) {
    message.error(e.message || t.value.login.loginFailed)
  } finally {
    loading.value = false
  }
}

async function handleChangePassword() {
  if (!pwdForm.new_password || pwdForm.new_password.length < 10) {
    message.error(t.value.login.mustChangePwdTooShort ?? 'Password must be at least 10 characters')
    return
  }
  if (!/[A-Z]/.test(pwdForm.new_password)) {
    message.error('Password must contain at least one uppercase letter')
    return
  }
  if (!/[a-z]/.test(pwdForm.new_password)) {
    message.error('Password must contain at least one lowercase letter')
    return
  }
  if (!/\d/.test(pwdForm.new_password)) {
    message.error('Password must contain at least one digit')
    return
  }
  if (!/[!@#$%^&*\-_+=?]/.test(pwdForm.new_password)) {
    message.error('Password must contain at least one special character (!@#$%^&*-_+=?)')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    message.error(t.value.login.mustChangePwdMismatch ?? 'Passwords do not match')
    return
  }
  if (pwdForm.new_password === tempOldPassword.value) {
    message.error(t.value.login.mustChangePwdSame ?? 'New password must differ from the temporary one')
    return
  }
  if (!authStore.user) return
  pwdLoading.value = true
  try {
    await userApi.changePassword(authStore.user.id, {
      old_password: tempOldPassword.value,
      new_password: pwdForm.new_password,
    })
    authStore.clearMustChangePassword()
    message.success(t.value.login.mustChangePwdSuccess ?? 'Password updated')
    showChangePwd.value = false
    router.push('/')
  } catch (e: any) {
    message.error(e.message || 'Failed to change password')
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1B4F8A 0%, #2E75B6 100%);
}

.login-card {
  width: 400px;
  background: #fff;
  border-radius: 12px;
  padding: 40px 36px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  font-size: 48px;
  margin-bottom: 12px;
}

.login-title {
  font-size: 22px;
  font-weight: 600;
  color: #1B4F8A;
  margin-bottom: 6px;
}

.login-subtitle {
  font-size: 12px;
  color: #999;
}
</style>