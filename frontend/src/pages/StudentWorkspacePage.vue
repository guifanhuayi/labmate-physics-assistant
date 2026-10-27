<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import { stage4Api, type StudentAssignmentSummary } from '../api/stage4'
import { cacheRead, cacheWrite } from '../drafts/cache'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const assignments = ref<StudentAssignmentSummary[]>([])
const loading = ref(true)
const warning = ref('')

onMounted(async () => {
  const key = `user:${auth.user?.id}:assignments`
  try {
    assignments.value = await stage4Api.studentAssignments()
    try { await cacheWrite(key, assignments.value) }
    catch { warning.value = '任务已加载，但本机暂存不可用，请检查浏览器存储权限。' }
  } catch {
    try {
      assignments.value = await cacheRead<StudentAssignmentSummary[]>(key) || []
      warning.value = assignments.value.length ? '当前离线，显示本机缓存的实验任务。' : '暂时无法读取实验任务，请联网后重试。'
    } catch { warning.value = '暂时无法读取实验任务，请联网后重试。' }
  } finally { loading.value = false }
})

async function signOut() { await auth.logout(); await router.replace('/login') }
</script>

<template>
  <div class="workspace-page student-page">
    <header class="workspace-header">
      <BrandLockup />
      <nav aria-label="当前工作台"><span class="active-nav">学生工作台</span></nav>
      <div class="account-menu"><span>{{ auth.user?.name }}</span><small>{{ auth.user?.account }}</small><button type="button" @click="signOut">退出</button></div>
    </header>
    <main class="workspace-shell student-shell">
      <section class="workspace-intro">
        <div><p class="eyebrow">阶段 4 · 数据录入</p><h1>我的实验任务</h1><p>按教师发布的模板记录数据；草稿自动保存在本机并同步到服务器。</p></div>
        <span class="verified-badge">{{ auth.user?.name }}</span>
      </section>
      <p v-if="warning" class="form-error" role="status">{{ warning }}</p>
      <section class="work-panel">
        <h2>班级实验</h2>
        <p v-if="loading">正在读取实验任务…</p>
        <p v-else-if="!assignments.length">尚无可查看的实验任务。</p>
        <div v-else class="student-assignment-list">
          <article v-for="item in assignments" :key="item.id" class="student-assignment-card">
            <div><strong>{{ item.title }}</strong><p>模板版本 v{{ item.versionNumber }} · {{ item.groupSharingEnabled ? '教师已开启组内共享' : '个人数据' }}</p><small>开放 {{ new Date(item.startAt).toLocaleString('zh-CN') }} — 截止 {{ new Date(item.dueAt).toLocaleString('zh-CN') }}</small></div>
            <button type="button" class="secondary-button" @click="router.push(`/student/assignments/${item.id}`)">{{ item.editable ? '录入数据' : '查看任务' }}</button>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.student-shell { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
.student-assignment-list { display: grid; gap: 14px; margin-top: 18px; }
.student-assignment-card { display: flex; align-items: stretch; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid #b9c9db; background: #fff; overflow-wrap: anywhere; }
.student-assignment-card > div { min-width: 0; }
.student-assignment-card button { margin: 0; }
.student-assignment-card strong { font-size: 1.1rem; }
.student-assignment-card p { margin: 8px 0; }
.student-assignment-card small { color: #647477; }
@media (min-width: 768px) {
  .student-assignment-card { align-items: center; flex-direction: row; justify-content: space-between; gap: 20px; }
  .student-assignment-card button { flex: 0 0 132px; width: auto; }
}
</style>
