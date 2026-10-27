<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { flushSync } from 'react-dom'
import { CommandType, Direction, LocaleType, mergeLocales, Univer, type IDisposable, type IRange } from '@univerjs/core'
import { FUniver } from '@univerjs/core/facade'
import { UniverDocsPlugin } from '@univerjs/docs'
import { UniverDocsUIPlugin } from '@univerjs/docs-ui'
import { UniverRenderEnginePlugin } from '@univerjs/engine-render'
import { SetRangeValuesMutation, SetSelectionsOperation, UniverSheetsPlugin, type ISetRangeValuesMutationParams, type ISetSelectionsOperationParams } from '@univerjs/sheets'
import { ExpandSelectionCommand, MoveSelectionCommand, SelectAllCommand, UniverSheetsUIPlugin } from '@univerjs/sheets-ui'
import { UniverUIPlugin } from '@univerjs/ui'
import DesignZhCN from '@univerjs/design/locale/zh-CN'
import DocsUIZhCN from '@univerjs/docs-ui/locale/zh-CN'
import SheetsZhCN from '@univerjs/sheets/locale/zh-CN'
import SheetsUIZhCN from '@univerjs/sheets-ui/locale/zh-CN'
import UIZhCN from '@univerjs/ui/locale/zh-CN'
import '@univerjs/ui/facade'
import '@univerjs/docs-ui/facade'
import '@univerjs/sheets/facade'
import '@univerjs/sheets-ui/facade'
import '@univerjs/design/lib/index.css'
import '@univerjs/ui/lib/index.css'
import '@univerjs/docs-ui/lib/index.css'
import '@univerjs/sheets-ui/lib/index.css'
import { cellAt, type CellRange, type TemplateTable } from '../templates/designer'
import { applyLabelEdits, labelEditsFromUniver, tableGrid, tableToUniverWorkbook, type LabelEdit } from '../templates/univerAdapter'

const props = defineProps<{ table: TemplateTable; selection: CellRange | null }>()
const emit = defineEmits<{
  selection: [range: CellRange]
  edit: [edits: LabelEdit[]]
  paste: [text: string]
  history: [direction: 'undo' | 'redo']
  requestEdit: [row: number, column: number]
  error: [message: string]
}>()
const host = ref<HTMLElement | null>(null)
const workbookId = `labmate-${crypto.randomUUID()}`
let instance: { univer: Univer; univerAPI: FUniver } | null = null
let owner: Univer | null = null
let subscriptions: IDisposable[] = []
let updating = false
let disposed = false
let lastProjection = ''
let refreshTimer: ReturnType<typeof setTimeout> | undefined

function publishSelection(ranges: IRange[]) {
  const range = ranges[0]
  if (!range) return
  const grid = tableGrid(props.table)
  emit('selection', { startRow: Math.max(0, range.startRow), startColumn: Math.max(0, range.startColumn),
    endRow: Math.min(grid.rows - 1, range.endRow), endColumn: Math.min(grid.columns - 1, range.endColumn) })
}

function readSelection() {
  const range = instance?.univerAPI.getActiveWorkbook()?.getActiveSheet().getSelection()?.getActiveRange()?.getRange()
  if (range) publishSelection([range])
}

function pointerSelection() { queueMicrotask(readSelection) }

function disposeOwner() {
  if (!owner) return
  // Drain React's pending workbook effects while their model still exists, before
  // Univer disposes it. Vue otherwise may remove the canvas between React frames.
  flushSync(() => {})
  const current = owner
  owner = null
  flushSync(() => current.dispose())
}

function pasteClipboard(event: ClipboardEvent) {
  if (!event.clipboardData?.types.includes('text/plain')) return
  event.preventDefault()
  event.stopImmediatePropagation()
  readSelection()
  emit('paste', event.clipboardData.getData('text/plain'))
}

function syncCanvas() {
  if (!instance || disposed) return
  const signature = JSON.stringify(props.table)
  if (lastProjection === signature) return
  updating = true
  try {
    instance.univerAPI.disposeUnit(workbookId)
    const workbook = instance.univerAPI.createWorkbook(tableToUniverWorkbook(props.table, workbookId))
    const grid = tableGrid(props.table)
    const range = props.selection
    const row = Math.min(range?.startRow ?? 0, grid.rows - 1)
    const column = Math.min(range?.startColumn ?? 0, grid.columns - 1)
    workbook.getActiveSheet().getRange(row, column,
      Math.max(1, Math.min(range?.endRow ?? row, grid.rows - 1) - row + 1),
      Math.max(1, Math.min(range?.endColumn ?? column, grid.columns - 1) - column + 1)).activate()
    lastProjection = signature
  } finally { updating = false }
}

async function flush() {
  const workbook = instance?.univerAPI.getActiveWorkbook()
  if (workbook?.isCellEditing() && !await workbook.endEditingAsync(true)) {
    throw new Error('表格中的文字尚未确认，请先完成或取消当前编辑。')
  }
}
defineExpose({ flush })

watch(() => JSON.stringify(props.table), () => {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(syncCanvas, 80)
})

function historyShortcut(event: KeyboardEvent) {
  const directions: Record<string, Direction> = { ArrowLeft: Direction.LEFT, ArrowRight: Direction.RIGHT,
    ArrowUp: Direction.UP, ArrowDown: Direction.DOWN, Tab: event.shiftKey ? Direction.LEFT : Direction.RIGHT }
  if (directions[event.key] !== undefined) {
    event.preventDefault()
    event.stopImmediatePropagation()
    const command = event.shiftKey && event.key !== 'Tab' ? ExpandSelectionCommand : MoveSelectionCommand
    void instance?.univerAPI.executeCommand(command.id, { direction: directions[event.key], jumpOver: event.ctrlKey || event.metaKey ? 1 : 0 })
      .then(readSelection).catch(error => emit('error', (error as Error).message))
    return
  }
  if (event.key === 'F2' || event.key === 'Enter') {
    event.preventDefault()
    event.stopImmediatePropagation()
    emit('requestEdit', props.selection?.startRow ?? 0, props.selection?.startColumn ?? 0)
    return
  }
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return
  const key = event.key.toLowerCase()
  if (key === 'a') {
    event.preventDefault()
    event.stopImmediatePropagation()
    void instance?.univerAPI.executeCommand(SelectAllCommand.id, { expandToGapFirst: false }).then(readSelection)
      .catch(error => emit('error', (error as Error).message))
    return
  }
  if (key !== 'z' && key !== 'y') return
  event.preventDefault()
  event.stopImmediatePropagation()
  void flush().then(() => emit('history', key === 'y' || event.shiftKey ? 'redo' : 'undo'))
    .catch(error => emit('error', (error as Error).message))
}

onMounted(() => {
  try {
    // Keep document focus visible to Univer's shortcut service. Global LabMate form rules
    // explicitly exclude this subtree, so native controls retain their own sizing/styles.
    const container = host.value!
    container.addEventListener('keydown', historyShortcut, true)
    container.addEventListener('pointerup', pointerSelection)
    container.addEventListener('paste', pasteClipboard, true)
    // Register only the open-source canvas and text editor plugins we use.
    // No formula engine, file conversion service or collaboration plugin is loaded.
    const univer = new Univer({ locale: LocaleType.ZH_CN, locales: {
      [LocaleType.ZH_CN]: mergeLocales(DesignZhCN, UIZhCN, DocsUIZhCN, SheetsZhCN, SheetsUIZhCN),
    } })
    owner = univer
    univer.registerPlugin(UniverRenderEnginePlugin)
    univer.registerPlugin(UniverUIPlugin, { container, header: false, toolbar: false, contextMenu: false })
    univer.registerPlugin(UniverDocsPlugin)
    univer.registerPlugin(UniverDocsUIPlugin)
    univer.registerPlugin(UniverSheetsPlugin)
    univer.registerPlugin(UniverSheetsUIPlugin, { formulaBar: false, footer: false, allowArrowKeyWrapOnSheetBoundary: false })
    instance = { univer, univerAPI: FUniver.newAPI(univer) }
    const api = instance.univerAPI
    subscriptions = [
      api.addEvent(api.Event.SelectionChanged, event => {
        if (updating || event.workbook.getId() !== workbookId) return
        publishSelection(event.selections)
      }),
      api.addEvent(api.Event.BeforeSheetEditStart, event => {
        if (event.workbook.getId() !== workbookId) return
        event.cancel = true
        if (cellAt(tableGrid(props.table), event.row, event.column)?.kind !== 'label') {
          emit('error', '此格用于学生录入。请在下方配置测量项，或将用途改为“标题或说明”后编辑文字。')
        } else emit('requestEdit', event.row, event.column)
      }),
      api.addEvent(api.Event.BeforeSheetEditEnd, event => {
        if (!event.isConfirm || event.workbook.getId() !== workbookId) return
        try { applyLabelEdits(props.table, [{ row: event.row, column: event.column, text: event.value.toPlainText() }]) }
        catch (error) { event.cancel = true; emit('error', (error as Error).message) }
      }),
      api.addEvent(api.Event.BeforeClipboardPaste, event => {
        if (event.workbook.getId() !== workbookId) return
        event.cancel = true
        if (event.text !== undefined) emit('paste', event.text)
        else emit('error', '请从 Excel 复制单元格文字，或使用“粘贴表格文字”。')
      }),
      api.addEvent(api.Event.BeforeCommandExecute, event => {
        if (updating || event.type !== CommandType.MUTATION || !event.id.startsWith('sheet.')) return
        const params = event.params as ISetRangeValuesMutationParams
        if (params?.unitId && params.unitId !== workbookId) return
        if (event.id === SetRangeValuesMutation.id && params.cellValue) {
          try { labelEditsFromUniver(props.table, params.cellValue) }
          catch (error) { event.cancel = true; emit('error', (error as Error).message) }
        } else {
          event.cancel = true
          emit('error', '行列、合并、冻结和列宽请使用上方工具栏，字段绑定会一并保留。')
        }
      }),
      api.addEvent(api.Event.CommandExecuted, event => {
        if (updating) return
        if (event.id === SetSelectionsOperation.id) {
          const params = event.params as ISetSelectionsOperationParams
          if (params.unitId === workbookId) publishSelection(params.selections.map(selection => selection.range))
          return
        }
        if (event.id !== SetRangeValuesMutation.id) return
        const params = event.params as ISetRangeValuesMutationParams
        if (params.unitId !== workbookId || !params.cellValue) return
        const edits = labelEditsFromUniver(props.table, params.cellValue)
        lastProjection = JSON.stringify(applyLabelEdits(props.table, edits))
        emit('edit', edits)
      }),
    ]
    syncCanvas()
  } catch (error) {
    subscriptions.forEach(subscription => subscription.dispose())
    subscriptions = []
    disposeOwner()
    instance = null
    emit('error', `增强表格载入失败，可以切回原表格继续编辑。${error instanceof Error ? error.message : ''}`)
  }
})

onBeforeUnmount(() => {
  disposed = true
  clearTimeout(refreshTimer)
  subscriptions.forEach(subscription => subscription.dispose())
  subscriptions = []
  host.value?.removeEventListener('keydown', historyShortcut, true)
  host.value?.removeEventListener('pointerup', pointerSelection)
  host.value?.removeEventListener('paste', pasteClipboard, true)
  disposeOwner()
  instance = null
})
</script>

<template><div ref="host" class="univer-canvas-host" aria-label="增强实验表格画布" /></template>
