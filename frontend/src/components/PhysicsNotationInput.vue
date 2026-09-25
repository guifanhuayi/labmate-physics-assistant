<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { PHYSICS_COMMANDS, renderPhysicsNotation, type PhysicsCommand } from '../templates/physicsNotation'

const value = defineModel<string>()
defineProps<{ label: string; placeholder?: string }>()
const input = ref<HTMLInputElement | null>(null)
const prefix = ref<string | null>(null)
const search = ref('')
const panelOpen = ref(false)
const recent = ref<string[]>([])
const undo = ref<string[]>([])
const redo = ref<string[]>([])
const templateMode = ref(false)
const candidates = computed(() => prefix.value === null ? [] : PHYSICS_COMMANDS
  .filter((item) => item.command.slice(1).toLowerCase().startsWith(prefix.value!.toLowerCase()))
  .sort((a, b) => Number(recent.value.includes(b.command)) - Number(recent.value.includes(a.command)))
  .slice(0, 8))
const panelItems = computed(() => PHYSICS_COMMANDS
  .filter((item) => `${item.command} ${item.name} ${item.output}`.toLowerCase().includes(search.value.toLowerCase()))
  .sort((a, b) => Number(recent.value.includes(b.command)) - Number(recent.value.includes(a.command))))
const preview = computed(() => renderPhysicsNotation(value.value || ''))

function updatePrefix() {
  const element = input.value
  if (!element) return
  const before = (value.value || '').slice(0, element.selectionStart || 0)
  const match = before.match(/\\([A-Za-z]*)$/)
  prefix.value = match ? match[1] : null
}

function onTextInput(event: Event) {
  value.value = (event.target as HTMLInputElement).value
  undo.value = []
  redo.value = []
  updatePrefix()
}

async function accept(item: PhysicsCommand, fromPanel = false) {
  const element = input.value
  if (!element) return
  const current = value.value || ''
  const cursor = element.selectionStart || 0
  const start = fromPanel ? cursor : cursor - (prefix.value?.length || 0) - 1
  const end = fromPanel ? (element.selectionEnd || cursor) : cursor
  const insertion = item.template || item.output
  undo.value.push(current)
  redo.value = []
  value.value = current.slice(0, start) + insertion + current.slice(end)
  templateMode.value = Boolean(item.template)
  prefix.value = null
  panelOpen.value = false
  recent.value = [item.command, ...recent.value.filter((entry) => entry !== item.command)].slice(0, 10)
  await nextTick()
  element.focus()
  const position = start + (item.cursor ?? insertion.length)
  element.setSelectionRange(position, position)
}

function handleKey(event: KeyboardEvent) {
  if (event.key === 'Escape') { prefix.value = null; panelOpen.value = false; return }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && undo.value.length) {
    event.preventDefault()
    redo.value.push(value.value || '')
    value.value = undo.value.pop() || ''
    prefix.value = null
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y' && redo.value.length) {
    event.preventDefault()
    undo.value.push(value.value || '')
    value.value = redo.value.pop() || ''
    prefix.value = null
    return
  }
  if (prefix.value !== null && candidates.value.length && ['Tab', ' ', 'Enter'].includes(event.key)) {
    event.preventDefault()
    void accept(candidates.value[0])
    return
  }
  if (event.key === 'Tab' && templateMode.value && input.value) {
    const next = (value.value || '').indexOf('{', input.value.selectionStart || 0)
    if (next !== -1) {
      event.preventDefault()
      input.value.setSelectionRange(next + 1, next + 1)
    } else templateMode.value = false
  }
}
</script>

<template>
  <div class="physics-input">
    <label>{{ label }}<input ref="input" :value="value" :aria-label="label" :placeholder="placeholder" autocomplete="off" spellcheck="false" @input="onTextInput" @click="updatePrefix" @keyup="updatePrefix" @keydown="handleKey" /></label>
    <div v-if="prefix !== null && candidates.length" class="physics-candidates" role="listbox" aria-label="符号候选">
      <button v-for="item in candidates" :key="item.command" type="button" @mousedown.prevent @click="accept(item)"><code>{{ item.command }}</code><strong>{{ item.output }}</strong><span>{{ item.name }}</span></button>
    </div>
    <div v-if="value" class="physics-preview"><span>预览</span><span v-html="preview" /></div>
    <button class="physics-panel-toggle" type="button" @click="panelOpen = !panelOpen">{{ panelOpen ? '收起符号' : '查找符号与公式模板' }}</button>
    <div v-if="panelOpen" class="physics-panel">
      <input v-model="search" aria-label="搜索符号" placeholder="搜索命令、符号或中文名称" />
      <div><button v-for="item in panelItems" :key="item.command" type="button" @mousedown.prevent @click="accept(item, true)"><code>{{ item.command }}</code><strong>{{ item.output }}</strong><span>{{ item.name }}</span></button></div>
    </div>
  </div>
</template>
