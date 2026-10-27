<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import type { AdminSection, AdminMount } from '../admin/types'

const host = ref<HTMLElement | null>(null)
const loading = ref(true)
const failed = ref(false)
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const sections: AdminSection[] = ['overview', 'classes', 'roster', 'teachers']
const section = computed<AdminSection>(() => sections.includes(route.query.section as AdminSection)
  ? route.query.section as AdminSection : 'overview')
let mounted: AdminMount | undefined
let disposed = false

function props() {
  return {
    section: section.value,
    user: { name: auth.user?.name || '', account: auth.user?.account || '' },
    demoEnabled: !!auth.mode?.demoEnabled,
    onNavigate: (next: AdminSection) => { void router.replace({ path: '/admin', query: { section: next } }) },
    onLogout: async () => { await auth.logout(); await router.replace('/login') },
  }
}
async function load() {
  loading.value = true
  failed.value = false
  try {
    const { mountAdmin } = await import('../admin/mount')
    if (disposed || !host.value) return
    mounted = mountAdmin(host.value, props())
  } catch { failed.value = true }
  finally { loading.value = false }
}
onMounted(load)
watch([section, () => auth.user, () => auth.mode], () => mounted?.update(props()))
onBeforeUnmount(() => { disposed = true; mounted?.unmount() })
</script>

<template>
  <div class="admin-page">
    <p v-if="loading" class="admin-loading" role="status">正在加载管理员后台…</p>
    <div v-if="failed" class="admin-loading" role="alert">管理员后台加载失败。<button type="button" @click="load">重试加载</button></div>
    <div ref="host" class="admin-pro-host" />
  </div>
</template>

<style scoped>
.admin-page, .admin-pro-host { min-height: 100dvh; }
.admin-loading { margin: 0; padding: 32px; }
.admin-loading button { margin-left: 16px; }
</style>
