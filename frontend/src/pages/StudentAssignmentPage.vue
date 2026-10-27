<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import { ApiError } from '../api/client'
import { stage4Api, type DataSnapshot, type StudentAssignment } from '../api/stage4'
import { cacheRead, cacheWrite, type CachedData } from '../drafts/cache'
import { mergeValues, type Values } from '../drafts/merge'
import { normalizeTemplateSchema, type SpreadsheetCell, type TemplateField, type TemplateTable } from '../templates/designer'
import { renderPhysicsNotation } from '../templates/physicsNotation'
import { useAuthStore } from '../stores/auth'

type Kind = 'draft' | 'shared'
type SaveStatus = '本地已保存' | '已同步' | '同步失败' | '存在冲突'
interface DatasetState {
  version: number
  base: Values
  values: Values
  remote: Values
  conflicts: string[]
  status: SaveStatus
  error: string
  sources: Record<string, { editorId: string; editorName: string; editedAt: string }>
  inFlight: boolean
  generation: number
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = String(route.params.id)
const assignment = ref<StudentAssignment | null>(null)
const loading = ref(true)
const pageError = ref('')
const pageWarning = ref('')
const offline = ref(!navigator.onLine)
const keypadMedia = window.matchMedia('(max-width: 1024px), (pointer: coarse)')
const mobileKeypad = ref(keypadMedia.matches)
const activeNumeric = ref<{ table: TemplateTable; cell: SpreadsheetCell; field: TemplateField } | null>(null)
const keypadElement = ref<HTMLElement | null>(null)
const headerElement = ref<HTMLElement | null>(null)
let numericInput: HTMLElement | null = null
let resizeFrame = 0
const draft = reactive<DatasetState>(makeState())
const shared = reactive<DatasetState>(makeState())
const schema = computed(() => assignment.value
  ? normalizeTemplateSchema(JSON.parse(JSON.stringify(assignment.value.schema)), assignment.value.title, '') : null)
const saveChains: Record<Kind, Promise<void>> = { draft: Promise.resolve(), shared: Promise.resolve() }
const timers: Partial<Record<Kind, ReturnType<typeof setTimeout>>> = {}

function makeState(): DatasetState {
  return { version: 0, base: {}, values: {}, remote: {}, conflicts: [], status: '本地已保存', error: '', sources: {}, inFlight: false, generation: 0 }
}
function stateFor(kind: Kind) { return kind === 'draft' ? draft : shared }
function equalValues(left: Values, right: Values) {
  const keys = Object.keys(left)
  return keys.length === Object.keys(right).length && keys.every((key) => left[key] === right[key])
}
function cacheKey(kind: Kind) {
  const suffix = kind === 'shared' ? `shared:${assignment.value?.group?.id}` : 'draft'
  return `user:${auth.user?.id}:assignment:${id}:${suffix}`
}
function formatError(field: TemplateField, value: string): string {
  if (!value.trim()) return ''
  if (field.type === 'number' && !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return '请输入有效数值'
  if (field.type === 'integer' && !/^[+-]?\d+$/.test(value)) return '请输入整数'
  if (field.type === 'enum' && !(field.options || []).includes(value)) return '请选择有效选项'
  if (field.type === 'time' && Number.isNaN(Date.parse(value))) return '请输入有效时间'
  return ''
}
function valueKey(table: TemplateTable, cell: SpreadsheetCell) { return `${table.id}:${cell.id}` }
function fieldFor(table: TemplateTable, cell: SpreadsheetCell) { return table.fields.find((field) => field.key === cell.fieldKey) }
function kindFor(field: TemplateField): Kind { return assignment.value?.groupSharingEnabled && field.scope === 'group' ? 'shared' : 'draft' }
function stateForField(field: TemplateField) { return stateFor(kindFor(field)) }
function rowCells(table: TemplateTable, row: number) { return (table.grid?.cells || []).filter((cell) => cell.row === row).sort((a, b) => a.column - b.column) }
function hasFormatErrors(kind: Kind) {
  return schema.value?.tables.some((table) => table.grid?.cells.some((cell) => {
    const field = fieldFor(table, cell)
    return field && kindFor(field) === kind && formatError(field, stateFor(kind).values[valueKey(table, cell)] || '')
  })) || false
}
const missingRequired = computed(() => schema.value?.tables.reduce((count, table) => count + (table.grid?.cells || []).filter((cell) => {
  const field = fieldFor(table, cell)
  return field?.required && !stateForField(field).values[valueKey(table, cell)]?.trim()
}).length, 0) || 0)

async function persist(kind: Kind) {
  const state = stateFor(kind)
  const snapshot: CachedData = { version: state.version, baseValues: { ...state.base }, values: { ...state.values }, updatedAt: new Date().toISOString() }
  saveChains[kind] = saveChains[kind].catch(() => undefined).then(() => cacheWrite(cacheKey(kind), snapshot))
  try {
    await saveChains[kind]
    if (state.status !== '存在冲突') state.status = '本地已保存'
  } catch {
    state.status = '同步失败'
    state.error = '浏览器本地存储不可用；请勿关闭本页，并检查存储权限。'
    return false
  }
  return true
}

function schedule(kind: Kind) {
  if (timers[kind]) clearTimeout(timers[kind])
  timers[kind] = setTimeout(() => void sync(kind), 650)
}

async function sync(kind: Kind) {
  const state = stateFor(kind)
  if (!assignment.value?.editable || !navigator.onLine || state.inFlight || state.conflicts.length || hasFormatErrors(kind)) return
  if (equalValues(state.values, state.base)) { state.status = '已同步'; return }
  state.inFlight = true
  const sent = { ...state.values }
  const generation = state.generation
  try {
    const result = kind === 'draft'
      ? await stage4Api.saveDraft(id, state.version, sent, crypto.randomUUID())
      : await stage4Api.saveShared(id, state.version, sent, crypto.randomUUID())
    state.version = result.version
    state.base = { ...result.values }
    state.sources = result.sources || {}
    if (generation === state.generation) state.values = { ...result.values }
    await persist(kind)
    if (generation === state.generation) state.status = '已同步'
    else schedule(kind)
    state.error = ''
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 409 && cause.details && 'values' in cause.details) {
      const latest = cause.details as unknown as DataSnapshot
      const merged = mergeValues(state.base, state.values, latest.values)
      state.version = latest.version
      state.base = { ...latest.values }
      state.remote = { ...latest.values }
      state.values = merged.merged
      state.conflicts = merged.conflicts
      state.sources = latest.sources || {}
      state.status = merged.conflicts.length ? '存在冲突' : '本地已保存'
      state.error = merged.conflicts.length ? '同一个录入格在其他设备或同组成员处也被修改，请逐项选择。' : ''
      await persist(kind)
      if (!merged.conflicts.length) schedule(kind)
    } else {
      state.status = '同步失败'
      state.error = cause instanceof ApiError ? cause.message : '当前无法连接服务器；已保存在本机，联网后会重试。'
    }
  } finally { state.inFlight = false }
}

async function updateValue(table: TemplateTable, cell: SpreadsheetCell, field: TemplateField, value: string) {
  const kind = kindFor(field)
  const state = stateFor(kind)
  const key = valueKey(table, cell)
  state.values = { ...state.values, [key]: value }
  state.generation += 1
  if (await persist(kind) && !formatError(field, value)) schedule(kind)
}
function changeValue(table: TemplateTable, cell: SpreadsheetCell, field: TemplateField, event: Event) {
  void updateValue(table, cell, field, (event.target as HTMLInputElement).value)
}
function keypadPress(token: string) {
  const target = activeNumeric.value
  if (!target) return
  if (token === '完成') { activeNumeric.value = null; return }
  const state = stateForField(target.field)
  const current = state.values[valueKey(target.table, target.cell)] || ''
  const next = token === '删除' ? current.slice(0, -1) : token === '清空' ? '' : current + token
  void updateValue(target.table, target.cell, target.field, next)
}

function onKeypadMediaChange(event: MediaQueryListEvent) {
  mobileKeypad.value = event.matches
  void keepNumericVisible()
}
async function focusField(table: TemplateTable, cell: SpreadsheetCell, field: TemplateField, event: FocusEvent) {
  activeNumeric.value = ['number', 'integer'].includes(field.type) ? { table, cell, field } : null
  numericInput = activeNumeric.value ? event.target as HTMLElement : null
  await keepNumericVisible()
}
async function keepNumericVisible() {
  await nextTick()
  if (!mobileKeypad.value || !activeNumeric.value || !numericInput) return
  // Keep the focused value above the touch keypad, including in landscape.
  const keypadTop = keypadElement.value?.getBoundingClientRect().top ?? window.innerHeight
  const headerBottom = Math.max(0, headerElement.value?.getBoundingClientRect().bottom || 0)
  const inputRect = numericInput.getBoundingClientRect()
  if (inputRect.bottom > keypadTop - 16) window.scrollBy({ top: inputRect.bottom - keypadTop + 24 })
  else if (inputRect.top < headerBottom + 16) window.scrollBy({ top: inputRect.top - headerBottom - 16 })
}
function onViewportResize() {
  cancelAnimationFrame(resizeFrame)
  resizeFrame = requestAnimationFrame(() => void keepNumericVisible())
}

async function resolveConflict(kind: Kind, key: string, choice: 'mine' | 'server') {
  const state = stateFor(kind)
  if (choice === 'server') {
    const values = { ...state.values }
    if (state.remote[key] === undefined) delete values[key]
    else values[key] = state.remote[key]
    state.values = values
  }
  state.conflicts = state.conflicts.filter((item) => item !== key)
  state.generation += 1
  if (await persist(kind) && !state.conflicts.length) schedule(kind)
}

function labelFor(key: string) {
  for (const table of schema.value?.tables || []) {
    const cell = table.grid?.cells.find((item) => valueKey(table, item) === key)
    if (cell) return `${table.title} · 第 ${cell.row + 1} 行 · ${fieldFor(table, cell)?.label || key}`
  }
  return key
}

async function initialize(kind: Kind) {
  const state = stateFor(kind)
  let cached: CachedData | null = null
  try { cached = await cacheRead<CachedData>(cacheKey(kind)) } catch { /* storage warning handled on save */ }
  if (cached) {
    state.version = cached.version
    state.base = cached.baseValues
    state.values = cached.values
    state.status = '本地已保存'
  }
  try {
    const latest = kind === 'draft' ? await stage4Api.draft(id) : await stage4Api.shared(id)
    const merged = cached ? mergeValues(cached.baseValues, cached.values, latest.values) : { merged: latest.values, conflicts: [] }
    state.version = latest.version
    state.base = { ...latest.values }
    state.remote = { ...latest.values }
    state.values = { ...merged.merged }
    state.conflicts = merged.conflicts
    state.sources = latest.sources || {}
    state.status = merged.conflicts.length ? '存在冲突' : equalValues(state.values, state.base) ? '已同步' : '本地已保存'
    await persist(kind)
    if (!merged.conflicts.length && equalValues(state.values, state.base)) state.status = '已同步'
    else if (!merged.conflicts.length) schedule(kind)
  } catch (cause) {
    if (!cached) state.error = cause instanceof ApiError ? cause.message : '服务器暂时不可用，尚无本地草稿。'
  }
}

function onOnline() { offline.value = false; void sync('draft'); if (assignment.value?.group) void sync('shared') }
function onOffline() { offline.value = true }

onMounted(async () => {
  keypadMedia.addEventListener('change', onKeypadMediaChange)
  window.addEventListener('resize', onViewportResize)
  const key = `user:${auth.user?.id}:assignment:${id}:template`
  try {
    assignment.value = await stage4Api.studentAssignment(id)
    try { await cacheWrite(key, assignment.value) }
    catch { pageWarning.value = '模板已加载，但本机暂存不可用，请检查浏览器存储权限。' }
  } catch (cause) {
    try { assignment.value = await cacheRead<StudentAssignment>(key) }
    catch { /* server error shown below */ }
    if (!assignment.value) pageError.value = cause instanceof ApiError ? cause.message : '无法读取实验任务。'
  }
  if (assignment.value) {
    await initialize('draft')
    if (assignment.value.groupSharingEnabled && assignment.value.group) await initialize('shared')
  }
  loading.value = false
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
})
onBeforeUnmount(() => {
  keypadMedia.removeEventListener('change', onKeypadMediaChange)
  window.removeEventListener('resize', onViewportResize)
  cancelAnimationFrame(resizeFrame)
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
  for (const timer of Object.values(timers)) clearTimeout(timer)
})
</script>

<template>
  <div class="workspace-page student-page" :class="{ 'has-numeric-keypad': mobileKeypad && activeNumeric }">
    <header ref="headerElement" class="workspace-header">
      <BrandLockup />
      <nav aria-label="学生实验"><button type="button" @click="router.push('/student')">← 我的实验</button></nav>
      <div class="account-menu"><span>{{ auth.user?.name }}</span><small>{{ auth.user?.account }}</small></div>
    </header>
    <main class="workspace-shell entry-shell">
      <p v-if="loading">正在读取已发布模板和草稿…</p>
      <p v-else-if="pageError" class="form-error" role="alert">{{ pageError }}</p>
      <template v-else-if="assignment && schema">
        <p v-if="pageWarning" class="form-error" role="alert">{{ pageWarning }}</p>
        <section class="workspace-intro">
          <div><p class="eyebrow">实验数据录入 · 模板 v{{ assignment.versionNumber }}</p><h1>{{ assignment.title }}</h1><p>{{ schema.description }}</p></div>
          <span class="verified-badge">{{ assignment.editable ? '录入开放中' : '只读' }}</span>
        </section>
        <p v-if="offline" class="entry-notice" role="status">当前离线。录入会先保存在本机，联网后自动同步。</p>
        <p v-if="!assignment.editable" class="entry-notice">当前不在开放时间内，数据不可修改。</p>
        <p v-if="assignment.groupSharingEnabled && !assignment.group" class="entry-notice">教师已开启组内共享，但你尚未被分组；组内共享的数据暂不可录入。</p>
        <section class="entry-status" aria-live="polite">
          <span>个人草稿：<strong>{{ draft.status }}</strong></span>
          <span v-if="assignment.group">{{ assignment.group.name }}共享数据：<strong>{{ shared.status }}</strong></span>
          <span>尚有 {{ missingRequired }} 个必填格未录入；正式提交功能将在下一阶段开放。</span>
          <button v-if="draft.status === '同步失败'" type="button" class="secondary-button" @click="sync('draft')">重试同步个人草稿</button>
          <button v-if="assignment.group && shared.status === '同步失败'" type="button" class="secondary-button" @click="sync('shared')">重试同步组内数据</button>
        </section>
        <p v-if="draft.error" class="form-error" role="alert">个人草稿：{{ draft.error }}</p>
        <p v-if="shared.error" class="form-error" role="alert">共享数据：{{ shared.error }}</p>
        <section v-for="kind in (['draft', 'shared'] as const)" :key="kind" v-show="stateFor(kind).conflicts.length" class="work-panel conflict-panel">
          <h2>{{ kind === 'draft' ? '个人草稿' : '组内数据' }}存在冲突</h2>
          <p>请选择每个录入格保留的值，未解决前不会覆盖服务器。</p>
          <div v-for="key in stateFor(kind).conflicts" :key="key" class="conflict-item">
            <strong>{{ labelFor(key) }}</strong><span>我的值：{{ stateFor(kind).values[key] || '空' }}</span><span>服务器值：{{ stateFor(kind).remote[key] || '空' }}</span>
            <button type="button" class="secondary-button" @click="resolveConflict(kind, key, 'mine')">保留我的</button>
            <button type="button" class="secondary-button" @click="resolveConflict(kind, key, 'server')">采用服务器</button>
          </div>
        </section>
        <section v-if="schema.steps.length" class="work-panel">
          <h2>实验操作</h2><ol><li v-for="step in schema.steps" :key="step.id"><strong>{{ step.title }}</strong>　{{ step.instruction }}</li></ol>
        </section>
        <section v-for="table in schema.tables" :key="table.id" class="work-panel entry-table-panel">
          <h2>{{ table.title }}</h2><p v-if="table.description">{{ table.description }}</p>
          <p v-if="(table.grid?.columns || 0) > 1" class="entry-scroll-hint">左右滑动表格查看其他测量项，页面可上下滚动。</p>
          <div class="entry-table-scroll" role="region" :aria-label="`${table.title}，可横向滚动`" tabindex="0"><table class="entry-table" :style="{ '--entry-columns': table.grid?.columns || 1 }"><tbody>
            <tr v-for="row in table.grid?.rows || 0" :key="row">
              <template v-for="cell in rowCells(table, row - 1)" :key="cell.id">
                <th v-if="cell.kind === 'label'" :rowspan="cell.rowSpan" :colspan="cell.colSpan" scope="col" v-html="renderPhysicsNotation(cell.text)" />
                <td v-else :rowspan="cell.rowSpan" :colspan="cell.colSpan">
                  <template v-if="fieldFor(table, cell)">
                    <label :for="`${table.id}-${cell.id}`" class="entry-label"><span v-html="renderPhysicsNotation(fieldFor(table, cell)?.label || '')" /><span v-if="fieldFor(table, cell)?.required" aria-label="必填"> *</span></label>
                    <div class="entry-input-line">
                      <span v-if="fieldFor(table, cell)?.symbol" class="entry-symbol"><span v-html="renderPhysicsNotation(fieldFor(table, cell)?.symbol || '')" /> =</span>
                      <select v-if="fieldFor(table, cell)?.type === 'enum'" :id="`${table.id}-${cell.id}`" :value="stateForField(fieldFor(table, cell)!).values[valueKey(table, cell)] || ''" :disabled="!assignment.editable || (kindFor(fieldFor(table, cell)!) === 'shared' && !assignment.group)" @focus="activeNumeric = null" @change="changeValue(table, cell, fieldFor(table, cell)!, $event)"><option value="">请选择</option><option v-for="option in fieldFor(table, cell)?.options || []" :key="option" :value="option">{{ option }}</option></select>
                      <input v-else :id="`${table.id}-${cell.id}`" :value="stateForField(fieldFor(table, cell)!).values[valueKey(table, cell)] || ''" :inputmode="mobileKeypad && ['number', 'integer'].includes(fieldFor(table, cell)!.type) ? 'none' : fieldFor(table, cell)?.type === 'integer' ? 'numeric' : fieldFor(table, cell)?.type === 'number' ? 'decimal' : 'text'" :readonly="mobileKeypad && ['number', 'integer'].includes(fieldFor(table, cell)!.type)" :type="fieldFor(table, cell)?.type === 'time' ? 'datetime-local' : 'text'" :disabled="!assignment.editable || fieldFor(table, cell)?.type === 'image' || (kindFor(fieldFor(table, cell)!) === 'shared' && !assignment.group)" :aria-invalid="!!formatError(fieldFor(table, cell)!, stateForField(fieldFor(table, cell)!).values[valueKey(table, cell)] || '')" @focus="focusField(table, cell, fieldFor(table, cell)!, $event)" @input="changeValue(table, cell, fieldFor(table, cell)!, $event)" />
                      <span v-if="fieldFor(table, cell)?.unit" class="entry-unit" v-html="renderPhysicsNotation(fieldFor(table, cell)?.unit || '')" />
                    </div>
                    <small v-if="kindFor(fieldFor(table, cell)!) === 'shared'" class="entry-source">组内共享<span v-if="shared.sources[valueKey(table, cell)]"> · {{ shared.sources[valueKey(table, cell)].editorName }} 于 {{ new Date(shared.sources[valueKey(table, cell)].editedAt).toLocaleString('zh-CN') }} 修改</span></small>
                    <small v-if="formatError(fieldFor(table, cell)!, stateForField(fieldFor(table, cell)!).values[valueKey(table, cell)] || '')" class="entry-error">{{ formatError(fieldFor(table, cell)!, stateForField(fieldFor(table, cell)!).values[valueKey(table, cell)] || '') }}</small>
                  </template>
                </td>
              </template>
            </tr>
          </tbody></table></div>
        </section>
      </template>
    </main>
    <aside v-if="mobileKeypad && activeNumeric" ref="keypadElement" class="numeric-keypad" aria-label="实验数据数字键盘">
      <div class="keypad-heading">
        <span class="keypad-symbol" v-html="renderPhysicsNotation(`${activeNumeric.field.label} ${activeNumeric.field.symbol || ''} / ${activeNumeric.field.unit || ''}`)" />
        <output aria-label="当前数值">{{ stateForField(activeNumeric.field).values[valueKey(activeNumeric.table, activeNumeric.cell)] || '未填写' }}</output>
      </div>
      <div class="keypad-keys"><button v-for="token in ['1','2','3','4','5','6','7','8','9','−','0','.', '删除', '清空', '完成']" :key="token" type="button" :aria-label="token === '−' ? '负号' : token" @click="keypadPress(token === '−' ? '-' : token)">{{ token }}</button></div>
    </aside>
  </div>
</template>

<style scoped>
.entry-shell { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
.entry-notice { margin: 0; padding: 12px 16px; border-radius: 10px; background: #fff4da; color: #614315; }
.entry-status { display: flex; gap: 18px; flex-wrap: wrap; padding: 12px 16px; border-radius: 10px; background: #e8f3f0; }
.entry-status span { font-size: .91rem; }
.entry-table-panel { min-width: 0; }
.entry-table-panel h2 { margin-bottom: 8px; }
.entry-scroll-hint { color: #526b80; font-size: .875rem; }
.entry-table-scroll { overflow-x: auto; width: 100%; margin-top: 12px; overscroll-behavior-x: contain; }
.entry-table-scroll:focus-visible { outline: 3px solid #2369b6; outline-offset: 2px; }
.entry-table { --entry-cell-width: 184px; width: max(100%, calc(var(--entry-columns) * var(--entry-cell-width))); border-collapse: collapse; table-layout: fixed; }
.entry-table th, .entry-table td { border: 1px solid #d8e4e5; padding: 10px; vertical-align: top; overflow-wrap: anywhere; }
.entry-table th { background: #e9f2f0; text-align: left; }
.entry-label { display: block; font-size: .81rem; font-weight: 600; margin: 0 0 5px; }
.entry-input-line { display: flex; gap: 5px; align-items: center; }
.entry-input-line { flex-wrap: wrap; }
.entry-input-line input, .entry-input-line select { min-width: 0; flex: 1 1 88px; width: 100%; padding: 8px; font-size: 16px; }
.entry-symbol, .entry-unit { overflow-wrap: anywhere; max-width: 100%; font-size: .875rem; }
.entry-source { display: block; margin-top: 5px; color: #496864; }
.entry-error { display: block; margin-top: 5px; color: #ad3232; }
.numeric-keypad { position: fixed; z-index: 20; bottom: 0; left: 50%; transform: translateX(-50%); width: min(100%, 480px); max-height: 65dvh; overflow-y: auto; padding: 10px max(12px, env(safe-area-inset-right)) max(10px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)); border: 1px solid #9cb9cf; border-top: 3px solid #2369b6; background: #edf5fc; box-shadow: 0 -6px 24px #15344c30; }
.keypad-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; overflow-wrap: anywhere; }
.keypad-symbol { font-size: .875rem; }
.keypad-heading output { min-width: 0; font-size: 1.1rem; font-weight: 750; }
.keypad-keys { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
.keypad-keys button { min-height: 44px; border: 1px solid #9cb9cf; background: white; font-size: 1rem; touch-action: manipulation; }
.keypad-keys button:last-child { background: #176c62; color: white; border-color: #176c62; }
.has-numeric-keypad .entry-shell { padding-bottom: calc(390px + env(safe-area-inset-bottom)); }
.conflict-item { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 12px 0; border-top: 1px solid #ddd; }
.conflict-item span { padding: 6px; background: #f5f6f5; }
@media (min-width: 768px) { .entry-table { --entry-cell-width: 210px; } }
@media (max-height: 520px) {
  .keypad-keys { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .has-numeric-keypad .entry-shell { padding-bottom: calc(250px + env(safe-area-inset-bottom)); }
}
</style>
