<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const auth = useAuthStore()
const router = useRouter()

async function submit() {
  errorMessage.value = ''
  if (newPassword.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的新密码不一致。'
    return
  }
  submitting.value = true
  try {
    await auth.changePassword(currentPassword.value, newPassword.value)
    await router.replace(auth.homePath)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : '密码修改失败，请稍后再试。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="center-page">
    <section class="password-card" aria-labelledby="password-title">
      <BrandLockup />
      <div class="card-heading">
        <p>账号安全</p>
        <h1 id="password-title">修改初始密码</h1>
        <span>{{ auth.user?.name }}，完成修改后才能进入工作台。</span>
      </div>
      <form @submit.prevent="submit">
        <label for="current-password">当前初始密码</label>
        <input id="current-password" v-model="currentPassword" type="password" autocomplete="current-password" />
        <label for="new-password">新密码</label>
        <input id="new-password" v-model="newPassword" type="password" autocomplete="new-password" aria-describedby="password-rule" />
        <p id="password-rule" class="field-help">至少 12 位，同时包含字母和数字。</p>
        <label for="confirm-password">确认新密码</label>
        <input id="confirm-password" v-model="confirmPassword" type="password" autocomplete="new-password" />
        <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? '正在保存…' : '保存并进入工作台' }}
        </button>
      </form>
    </section>
  </main>
</template>
