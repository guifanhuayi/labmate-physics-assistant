<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const mode = ref<'login' | 'enrollment'>('login')
const account = ref('')
const password = ref('')
const enrollment = reactive({ name: '', studentNumber: '', phone: '', verificationCode: '', password: '', confirmPassword: '' })
const verificationSent = ref(false)
const submitting = ref(false)
const sendingCode = ref(false)
const errorMessage = ref('')
const statusMessage = ref('')
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const demoAuthEnabled = computed(() => auth.mode?.demoEnabled === true)
const demoAccounts = computed(() => auth.mode?.demoAccounts)

if (route.query.reason === 'network') errorMessage.value = '暂时无法连接服务器，请确认本地服务已启动。'

function showError(error: unknown) {
  errorMessage.value = error instanceof ApiError ? error.message : '暂时无法连接服务器，请稍后再试。'
  statusMessage.value = ''
}

function switchMode(next: 'login' | 'enrollment') {
  mode.value = next
  errorMessage.value = ''
  statusMessage.value = ''
}

async function submitLogin() {
  errorMessage.value = ''
  if (!account.value.trim() || !password.value) {
    errorMessage.value = demoAuthEnabled.value ? '请输入账号和任意非空密码。' : '请输入学号、手机号或工号以及密码。'
    return
  }
  submitting.value = true
  try {
    await auth.login(account.value, password.value)
    await router.replace(auth.homePath)
  } catch (error) {
    showError(error)
  } finally {
    submitting.value = false
  }
}

async function requestVerification() {
  errorMessage.value = ''
  statusMessage.value = ''
  if (!enrollment.name.trim() || !enrollment.studentNumber.trim() || !/^1[3-9]\d{9}$/.test(enrollment.phone)) {
    errorMessage.value = '请填写名单中的姓名、完整学号和有效手机号。'
    return
  }
  sendingCode.value = true
  try {
    const result = await auth.requestStudentVerification(enrollment.name, enrollment.studentNumber, enrollment.phone)
    verificationSent.value = true
    statusMessage.value = `验证码已发送，${Math.round(result.expiresInSeconds / 60)} 分钟内有效。`
  } catch (error) {
    showError(error)
  } finally {
    sendingCode.value = false
  }
}

async function completeEnrollment() {
  errorMessage.value = ''
  if (!verificationSent.value || !enrollment.verificationCode) {
    errorMessage.value = '请先获取并填写短信验证码。'
    return
  }
  if (enrollment.password !== enrollment.confirmPassword) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  submitting.value = true
  try {
    await auth.completeStudentEnrollment({
      name: enrollment.name,
      studentNumber: enrollment.studentNumber,
      phone: enrollment.phone,
      verificationCode: enrollment.verificationCode,
      password: enrollment.password,
    })
    await router.replace(auth.homePath)
  } catch (error) {
    showError(error)
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
        <p v-if="demoAuthEnabled">学生使用已导入名单中的学号登录；演示阶段密码填写任意非空内容。</p>
        <p v-else>登录后进入你的实验工作台。身份、模板版本和关键操作均由服务器验证并留痕。</p>
        <dl v-if="demoAuthEnabled">
          <div><dt>01</dt><dd>学生使用学号登录</dd></div>
          <div><dt>02</dt><dd>教师使用工号登录</dd></div>
          <div><dt>03</dt><dd>管理员使用管理员账号登录</dd></div>
        </dl>
        <dl v-else>
          <div><dt>01</dt><dd>学生首次自行设置密码</dd></div>
          <div><dt>02</dt><dd>学号或绑定手机号登录</dd></div>
          <div><dt>03</dt><dd>不同角色独立授权</dd></div>
        </dl>
      </div>
      <section class="auth-card" aria-labelledby="login-title">
        <BrandLockup />
        <div v-if="!demoAuthEnabled" class="auth-mode-switch" role="tablist" aria-label="登录方式">
          <button type="button" role="tab" :aria-selected="mode === 'login'" :class="{ active: mode === 'login' }" @click="switchMode('login')">账号登录</button>
          <button type="button" role="tab" :aria-selected="mode === 'enrollment'" :class="{ active: mode === 'enrollment' }" @click="switchMode('enrollment')">学生首次登录</button>
        </div>

        <template v-if="demoAuthEnabled || mode === 'login'">
          <div class="card-heading">
            <p>{{ demoAuthEnabled ? '演示模式' : '欢迎回来' }}</p>
            <h2 id="login-title">登录 LabMate</h2>
            <span v-if="demoAuthEnabled">学生填写已导入的学号，教师和管理员填写各自账号；密码任意填写。</span>
            <span v-else>学生可使用学号或已绑定手机号，教师使用工号登录。</span>
          </div>
          <form autocomplete="on" novalidate @submit.prevent="submitLogin">
            <label for="account">账号</label>
            <input id="account" v-model="account" name="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" :placeholder="demoAuthEnabled ? '学号、工号或管理员账号' : '学号、手机号、工号或管理员账号'" maxlength="64" />
            <label for="password">密码</label>
            <input id="password" v-model="password" name="password" type="password" autocomplete="current-password" :placeholder="demoAuthEnabled ? '任意非空内容' : '请输入密码'" maxlength="256" />
            <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
            <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? '正在验证…' : '登录' }}</button>
          </form>
          <p v-if="demoAuthEnabled" class="auth-note">演示登录：学生使用教师已导入名单中的学号；教师 {{ demoAccounts?.teacher }} · 管理员 {{ demoAccounts?.admin }}。不存在或未导入的学号不能登录。</p>
          <p v-else class="auth-note">学生账号不会因多次输错密码而锁定；系统仍会阻止异常批量尝试。</p>
        </template>

        <template v-else>
          <div class="card-heading">
            <p>无需初始密码或激活码</p>
            <h2 id="login-title">学生首次设置</h2>
            <span>姓名和学号必须与教师导入的名单完全一致。</span>
          </div>
          <form class="enrollment-form" novalidate @submit.prevent="completeEnrollment">
            <div class="two-fields">
              <div><label for="enrollment-name">姓名</label><input id="enrollment-name" v-model="enrollment.name" autocomplete="name" maxlength="80" /></div>
              <div><label for="student-number">学号</label><input id="student-number" v-model="enrollment.studentNumber" autocomplete="username" maxlength="64" /></div>
            </div>
            <label for="phone">手机号</label>
            <div class="verification-row">
              <input id="phone" v-model="enrollment.phone" inputmode="tel" autocomplete="tel" maxlength="11" placeholder="用于验证和后续登录" />
              <button class="secondary-button" type="button" :disabled="sendingCode" @click="requestVerification">{{ sendingCode ? '正在发送…' : '获取验证码' }}</button>
            </div>
            <label for="verification-code">短信验证码</label><input id="verification-code" v-model="enrollment.verificationCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" />
            <div class="two-fields">
              <div><label for="new-password">设置密码</label><input id="new-password" v-model="enrollment.password" type="password" autocomplete="new-password" maxlength="256" /></div>
              <div><label for="confirm-password">确认密码</label><input id="confirm-password" v-model="enrollment.confirmPassword" type="password" autocomplete="new-password" maxlength="256" /></div>
            </div>
            <p class="field-help">密码至少 12 位，并同时包含字母和数字。手机号验证成功后可用于登录。</p>
            <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
            <p v-if="statusMessage" class="success-message" role="status">{{ statusMessage }}</p>
            <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? '正在设置…' : '完成设置并登录' }}</button>
          </form>
        </template>
      </section>
    </section>
  </main>
</template>
