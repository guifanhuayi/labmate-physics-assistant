<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const account = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const demoAuthEnabled = import.meta.env.VITE_DEMO_AUTH_ENABLED === 'true'

if (route.query.reason === 'network') errorMessage.value = '暂时无法连接服务器，请确认本地服务已启动。'

async function submit() {
  errorMessage.value = ''
  if (!demoAuthEnabled && (!account.value.trim() || !password.value)) {
    errorMessage.value = '请输入账号和密码。'
    return
  }
  submitting.value = true
  try {
    await auth.login(account.value, password.value)
    await router.replace(auth.homePath)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : '暂时无法连接服务器，请稍后再试。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <header class="institution-bar">
      <BrandLockup compact />
      <span>大连理工大学公共基础学院物理实验室</span>
    </header>
    <section class="auth-layout">
      <div class="auth-context">
        <p class="eyebrow">大学物理实验</p>
        <h1>让每一次测量<br />都有可信记录</h1>
        <p>登录后进入你的实验工作台。计算、提交和审核将以服务器记录为准。</p>
        <dl>
          <div><dt>01</dt><dd>身份由服务器验证</dd></div>
          <div><dt>02</dt><dd>不同角色独立授权</dd></div>
          <div><dt>03</dt><dd>关键操作保留审计记录</dd></div>
        </dl>
      </div>
      <section class="auth-card" aria-labelledby="login-title">
        <BrandLockup />
        <div class="card-heading">
          <p>欢迎回来</p>
          <h2 id="login-title">登录 LabMate</h2>
          <span v-if="demoAuthEnabled">演示模式已开启，任意内容均可进入。</span>
          <span v-else>学生使用学号，教师使用工号登录。</span>
        </div>
        <form autocomplete="on" @submit.prevent="submit" novalidate>
          <label for="account">账号</label>
          <input
            id="account"
            v-model="account"
            name="username"
            type="text"
            autocomplete="username"
            autocapitalize="none"
            spellcheck="false"
            placeholder="学号、工号或管理员账号"
            maxlength="64"
          />
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            maxlength="256"
          />
          <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
          <button class="primary-button" type="submit" :disabled="submitting">
            {{ submitting ? '正在验证…' : '登录' }}
          </button>
        </form>
        <p v-if="demoAuthEnabled" class="auth-note">可直接登录；输入 admin 或 t0001 可体验对应角色，其他内容进入学生工作台。</p>
        <p v-else class="auth-note">可使用浏览器密码管理器安全保存登录信息。遇到账号停用请联系实验室管理员。</p>
      </section>
    </section>
  </main>
</template>
