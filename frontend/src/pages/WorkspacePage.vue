<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(true)
const errorMessage = ref('')
const roleLabel = computed(() => ({ student: '学生', teacher: '教师', admin: '管理员' })[auth.user?.role || 'student'])

onMounted(async () => {
  if (!auth.user) return
  try {
    await auth.loadWorkspace(auth.user.role)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : '工作台暂时无法加载。'
  } finally {
    loading.value = false
  }
})

async function signOut() {
  await auth.logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="workspace-page">
    <header class="workspace-header">
      <BrandLockup />
      <nav aria-label="当前工作台"><span class="active-nav">{{ roleLabel }}工作台</span></nav>
      <div class="account-menu">
        <span>{{ auth.user?.name }}</span>
        <small>{{ auth.user?.account }}</small>
        <button type="button" @click="signOut">退出</button>
      </div>
    </header>
    <main class="workspace-shell">
      <section class="workspace-intro">
        <div>
          <p class="eyebrow">身份验证已启用</p>
          <h1>{{ auth.workspace?.title || `${roleLabel}工作台` }}</h1>
          <p>{{ auth.workspace?.description || '正在读取工作台权限…' }}</p>
        </div>
        <span class="verified-badge">服务器已验证</span>
      </section>
      <p v-if="errorMessage" class="form-error panel-error" role="alert">{{ errorMessage }}</p>
      <section v-else class="empty-workspace" aria-live="polite">
        <div class="empty-symbol" aria-hidden="true">λ</div>
        <h2>{{ loading ? '正在加载工作台' : '基础工作台已经就绪' }}</h2>
        <p v-if="!loading">当前版本已开放真实身份、持久会话和角色权限。后续功能将按纵向业务切片逐步接入。</p>
        <div v-if="!loading" class="status-grid">
          <div><span>登录方式</span><strong>账号与密码</strong></div>
          <div><span>当前角色</span><strong>{{ roleLabel }}</strong></div>
          <div><span>权限来源</span><strong>服务端授权</strong></div>
        </div>
      </section>
    </main>
  </div>
</template>
