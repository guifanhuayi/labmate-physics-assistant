<script setup lang="ts">
import { computed, defineAsyncComponent, h, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { renderPhysicsNotation } from '../templates/physicsNotation'
import PhysicsNotationInput from './PhysicsNotationInput.vue'
import { applyLabelEdits, pasteTableText, type LabelEdit } from '../templates/univerAdapter'
import {
  cellAt,
  createMeasurementField,
  createSpreadsheetGrid,
  mergeSpreadsheetCells,
  resizeSpreadsheetGrid,
  splitSpreadsheetCell,
  type CellRange,
  type SpreadsheetCell,
  type SpreadsheetGrid,
  type TemplateTable,
} from '../templates/designer'

const table = defineModel<TemplateTable>({ required: true })
const selection = ref<CellRange | null>(null)
const localError = ref('')
const undoStack = ref<TemplateTable[]>([])
const redoStack = ref<TemplateTable[]>([])
const dragAnchor = ref<SpreadsheetCell | null>(null)
const dragging = ref(false)
const batchText = ref('')
const enhanced = ref(false)
const pasteOpen = ref(false)
const pasteText = ref('')
const canvas = ref<{ flush: () => Promise<void> } | null>(null)
const labelEditor = ref<HTMLElement | null>(null)
const editingLabel = ref<{ row: number; column: number; text: string } | null>(null)
const UniverTableCanvas = defineAsyncComponent({
  loader: () => import('./UniverTableCanvas.vue'),
  loadingComponent: { render: () => h('p', { class: 'sheet-help', role: 'status' }, '正在载入增强表格…') },
  delay: 0,
  onError(error, _retry, fail) {
    localError.value = `增强表格未能载入，已保留原表格。${error.message}`
    enhanced.value = false
    fail()
  },
})

async function flush() {
  if (editingLabel.value && !confirmLabelEdit()) throw new Error(localError.value)
  await canvas.value?.flush()
}
defineExpose({ flush })

async function editCanvasLabel(row: number, column: number) {
  const cell = cellAt(grid.value, row, column)
  if (cell?.kind !== 'label') {
    localError.value = '此格用于学生录入，请在下方配置测量项。'
    return
  }
  editingLabel.value = { row: cell.row, column: cell.column, text: cell.text }
  await nextTick()
  const input = labelEditor.value?.querySelector('input')
  input?.focus()
  input?.select()
}

function confirmLabelEdit() {
  if (!editingLabel.value) return true
  try {
    const next = applyLabelEdits(table.value, [editingLabel.value])
    if (JSON.stringify(next.grid) !== JSON.stringify(grid.value)) {
      rememberGrid()
      table.value = next
    }
    editingLabel.value = null
    localError.value = ''
    return true
  } catch (error) { localError.value = (error as Error).message; return false }
}

function labelEditorKey(event: KeyboardEvent) {
  if (event.defaultPrevented || event.isComposing) return
  if (event.key === 'Enter') { event.preventDefault(); confirmLabelEdit() }
  else if (event.key === 'Escape') { event.preventDefault(); editingLabel.value = null }
}

async function switchEditor(value: boolean) {
  try {
    await flush()
    enhanced.value = value
    localError.value = ''
  } catch (error) { localError.value = (error as Error).message }
}

function applyCanvasEdits(edits: LabelEdit[]) {
  try {
    const next = applyLabelEdits(table.value, edits)
    if (JSON.stringify(next.grid) === JSON.stringify(grid.value)) return
    rememberGrid()
    table.value = next
    localError.value = ''
  } catch (error) { localError.value = (error as Error).message }
}

function pasteTextAtSelection(text: string) {
  try {
    if (!selection.value) throw new Error('请先选择粘贴起点。')
    const next = pasteTableText(table.value, selection.value, text)
    rememberGrid()
    table.value = next
    localError.value = ''
    pasteOpen.value = false
    pasteText.value = ''
  } catch (error) { localError.value = (error as Error).message }
}

function stopDragging() { dragging.value = false }
onMounted(() => window.addEventListener('pointerup', stopDragging))
onUnmounted(() => window.removeEventListener('pointerup', stopDragging))

const grid = computed(() => {
  if (!table.value.grid) table.value.grid = createSpreadsheetGrid(table.value.fields, table.value.minimumRows)
  return table.value.grid
})

const selectedCell = computed(() => selection.value
  ? cellAt(grid.value, selection.value.startRow, selection.value.startColumn) || null
  : null)
const selectedCells = computed(() => grid.value.cells.filter(isSelected))
const selectedKind = computed(() => selectedCells.value.every((cell) => cell.kind === 'label') ? 'label'
  : selectedCells.value.every((cell) => cell.kind === 'field') ? 'field' : '')

const selectionLabel = computed(() => {
  if (!selection.value) return '尚未选择单元格'
  const start = `R${selection.value.startRow + 1}C${selection.value.startColumn + 1}`
  const end = `R${selection.value.endRow + 1}C${selection.value.endColumn + 1}`
  return start === end ? start : `${start}:${end}`
})

const selectedColumnWidth = computed(() => selectedCell.value ? grid.value.columnWidths[selectedCell.value.column] : 140)

function snapshotTable(): TemplateTable {
  // Template data is JSON-only; serialization unwraps nested Vue proxies as well.
  return JSON.parse(JSON.stringify(table.value)) as TemplateTable
}

function rememberGrid() {
  undoStack.value.push(snapshotTable())
  if (undoStack.value.length > 30) undoStack.value.shift()
  redoStack.value = []
}

function undo() {
  if (editingLabel.value && !confirmLabelEdit()) return
  const previous = undoStack.value.pop()
  if (!previous) return
  redoStack.value.push(snapshotTable())
  table.value = previous
  selection.value = null
}

function redo() {
  if (editingLabel.value && !confirmLabelEdit()) return
  const next = redoStack.value.pop()
  if (!next) return
  undoStack.value.push(snapshotTable())
  table.value = next
  selection.value = null
}

function cellsForRow(row: number) {
  return grid.value.cells.filter((cell) => cell.row === row).sort((a, b) => a.column - b.column)
}

function isSelected(cell: SpreadsheetCell) {
  if (!selection.value) return false
  const startRow = Math.min(selection.value.startRow, selection.value.endRow)
  const endRow = Math.max(selection.value.startRow, selection.value.endRow)
  const startColumn = Math.min(selection.value.startColumn, selection.value.endColumn)
  const endColumn = Math.max(selection.value.startColumn, selection.value.endColumn)
  return cell.row <= endRow && cell.row + cell.rowSpan - 1 >= startRow && cell.column <= endColumn && cell.column + cell.colSpan - 1 >= startColumn
}

function startSelection(event: PointerEvent, cell: SpreadsheetCell) {
  if (event.button !== 0) return
  event.preventDefault()
  localError.value = ''
  dragAnchor.value = cell
  dragging.value = true
  batchText.value = ''
  extendSelection(cell)
}

function extendSelection(cell: SpreadsheetCell) {
  const anchor = dragAnchor.value
  if (!anchor) return
  selection.value = {
    startRow: Math.min(anchor.row, cell.row),
    endRow: Math.max(anchor.row + anchor.rowSpan - 1, cell.row + cell.rowSpan - 1),
    startColumn: Math.min(anchor.column, cell.column),
    endColumn: Math.max(anchor.column + anchor.colSpan - 1, cell.column + cell.colSpan - 1),
  }
}

function dragInto(cell: SpreadsheetCell) {
  if (dragging.value) extendSelection(cell)
}

function mergeSelection() {
  if (!selection.value) return
  try {
    rememberGrid()
    table.value.grid = mergeSpreadsheetCells(grid.value, selection.value)
    const startRow = Math.min(selection.value.startRow, selection.value.endRow)
    const startColumn = Math.min(selection.value.startColumn, selection.value.endColumn)
    selection.value = { startRow, endRow: startRow, startColumn, endColumn: startColumn }
    localError.value = ''
  } catch (value) {
    localError.value = value instanceof Error ? value.message : '无法合并所选单元格。'
  }
}

function splitSelection() {
  if (!selection.value) return
  rememberGrid()
  table.value.grid = splitSpreadsheetCell(grid.value, selection.value.startRow, selection.value.startColumn, table.value.fields)
  selection.value = { ...selection.value, endRow: selection.value.startRow, endColumn: selection.value.startColumn }
  localError.value = ''
}

function resize(rows: number, columns: number) {
  const nextRows = Math.max(2, Math.min(201, Number.isFinite(rows) ? Math.round(rows) : grid.value.rows))
  const nextColumns = Math.max(1, Math.min(30, Number.isFinite(columns) ? Math.round(columns) : grid.value.columns))
  if (nextRows === grid.value.rows && nextColumns === grid.value.columns) return
  rememberGrid()
  const fields = [...table.value.fields]
  if (nextColumns > grid.value.columns) {
    while (fields.length < nextColumns) fields.push(createMeasurementField(table.value.id, fields.length, fields))
  }
  const resizedGrid = resizeSpreadsheetGrid(grid.value, nextRows, nextColumns, fields)
  const dataRows = nextRows - 1
  table.value = { ...table.value, fields, grid: resizedGrid, minimumRows: dataRows, maximumRows: dataRows }
  selection.value = null
  localError.value = ''
}

function updateSelectedText(value: string) {
  const targets = selectedCells.value.filter((cell) => cell.kind === 'label' && cell.text !== value)
  if (targets.length) {
    rememberGrid()
    targets.forEach((cell) => { cell.text = value })
  }
}

function updateSelectedKind(value: 'label' | 'field') {
  if (!selectedCells.value.length) return
  if (value === 'field' && selectedCells.value.some((cell) => cell.rowSpan > 1 || cell.colSpan > 1)) {
    localError.value = '已合并的单元格不能设为数据输入，请先拆分。'
    return
  }
  rememberGrid()
  selectedCells.value.forEach((cell) => {
    cell.kind = value
    if (value === 'field') {
      cell.fieldKey = cell.fieldKey || table.value.fields[cell.column]?.key || table.value.fields[0]?.key
      cell.text = ''
    } else delete cell.fieldKey
  })
  localError.value = ''
}

function updateSelectedField(value: string) {
  const targets = selectedCells.value.filter((cell) => cell.kind === 'field' && cell.fieldKey !== value)
  if (!targets.length) return
  rememberGrid()
  targets.forEach((cell) => { cell.fieldKey = value })
}

function updateColumnWidth(value: number) {
  if (!selectedCell.value) return
  rememberGrid()
  grid.value.columnWidths[selectedCell.value.column] = Math.max(80, Math.min(320, value))
}

function updateFrozenRows(value: number) {
  rememberGrid()
  grid.value.frozenRows = Math.max(0, Math.min(grid.value.rows, value))
}

function cellText(cell: SpreadsheetCell) {
  if (cell.kind === 'label') return cell.text || '空白'
  const field = table.value.fields.find((item) => item.key === cell.fieldKey)
  return field ? `${field.label}\n${field.symbol ? `${field.symbol} / ` : ''}${field.unit}` : '未选择测量项'
}
</script>

<template>
  <div class="spreadsheet-editor">
    <div class="sheet-mode-bar">
      <div class="sheet-mode-switch" role="group" aria-label="表格编辑方式">
        <button type="button" :aria-pressed="!enhanced" @click="switchEditor(false)">原表格</button>
        <button type="button" :aria-pressed="enhanced" @click="switchEditor(true)">增强表格</button>
      </div>
      <span>共用同一份模板，可随时切换；增强表格支持键盘选区和直接编辑标题。</span>
    </div>
    <div class="spreadsheet-toolbar">
      <div class="sheet-size-controls">
        <label>数据行数（不含表头）<input :value="grid.rows - 1" type="number" min="1" max="200" @change="resize(Number(($event.target as HTMLInputElement).value) + 1, grid.columns)" /></label>
        <label>测量列数<input :value="grid.columns" type="number" min="1" max="30" @change="resize(grid.rows, Number(($event.target as HTMLInputElement).value))" /></label>
      </div>
      <div class="sheet-actions">
        <button class="sheet-history-action" type="button" :disabled="!undoStack.length" @click="undo">撤销</button>
        <button class="sheet-history-action" type="button" :disabled="!redoStack.length" @click="redo">重做</button>
        <button class="sheet-add-action" type="button" @click="resize(grid.rows + 1, grid.columns)">＋ 行</button>
        <button class="sheet-remove-action" type="button" :disabled="grid.rows <= 2" @click="resize(grid.rows - 1, grid.columns)">－ 行</button>
        <button class="sheet-add-action" type="button" @click="resize(grid.rows, grid.columns + 1)">＋ 列</button>
        <button class="sheet-remove-action" type="button" :disabled="grid.columns <= 1" @click="resize(grid.rows, grid.columns - 1)">－ 列</button>
        <button class="sheet-structure-action" type="button" :disabled="!selection" @click="mergeSelection">合并选区</button>
        <button class="sheet-structure-action" type="button" :disabled="!selectedCell || (selectedCell.rowSpan === 1 && selectedCell.colSpan === 1)" @click="splitSelection">拆分单元格</button>
        <button class="sheet-structure-action" type="button" :disabled="!selection" @click="pasteOpen = !pasteOpen">粘贴表格文字</button>
      </div>
    </div>
    <div class="sheet-layout-controls">
      <label>冻结顶部行数<input :value="grid.frozenRows" type="number" min="0" :max="grid.rows" @change="updateFrozenRows(Number(($event.target as HTMLInputElement).value))" /></label>
      <label>所选列宽<input :value="selectedColumnWidth" type="range" min="80" max="320" step="10" :disabled="!selectedCell" @change="updateColumnWidth(Number(($event.target as HTMLInputElement).value))" /></label>
    </div>
    <p class="sheet-help">下方可直接修改每列的测量名称、符号和单位。按住鼠标左键拖动可框选多个单元格，统一设置用途或显示文字；数据输入格不能合并。</p>
    <p v-if="localError" class="sheet-error">{{ localError }}</p>
    <div v-if="pasteOpen" class="sheet-paste-panel">
      <label>从 Excel 复制后粘贴到这里<textarea v-model="pasteText" rows="3" aria-label="待粘贴的表格文字" /></label>
      <p class="field-help">从所选左上角开始，仅写入标题或说明。输入格请先在下方更改用途；超过表格范围会提示，不会截断。</p>
      <div class="sheet-actions"><button type="button" :disabled="!pasteText" @click="pasteTextAtSelection(pasteText)">应用粘贴</button><button type="button" @click="pasteOpen = false">取消</button></div>
    </div>
    <div v-if="enhanced" class="enhanced-sheet">
      <UniverTableCanvas ref="canvas" :table="table" :selection="selection"
        @selection="selection = $event" @edit="applyCanvasEdits" @paste="pasteTextAtSelection" @request-edit="editCanvasLabel"
        @history="$event === 'undo' ? undo() : redo()" @error="localError = $event" />
      <div v-if="editingLabel" ref="labelEditor" class="univer-label-editor" role="dialog" aria-label="编辑标题或说明" @keydown.stop="labelEditorKey">
        <PhysicsNotationInput v-model="editingLabel.text" label="标题或说明文字" />
        <div class="sheet-actions"><button type="button" @click="confirmLabelEdit">确认文字</button><button type="button" @click="editingLabel = null">取消编辑</button></div>
      </div>
    </div>
    <div v-else class="sheet-canvas">
      <table>
        <colgroup><col class="row-number-column" /><col v-for="(width, column) in grid.columnWidths" :key="column" :style="{ width: `${width}px` }" /></colgroup>
        <tbody>
          <tr v-for="row in grid.rows" :key="row" :class="{ 'frozen-sheet-row': row <= grid.frozenRows }" :style="{ '--freeze-top': `${(row - 1) * 44}px` }">
            <th class="row-number">{{ row }}</th>
            <td
              v-for="cell in cellsForRow(row - 1)"
              :key="cell.id"
              :rowspan="cell.rowSpan"
              :colspan="cell.colSpan"
              :class="['sheet-cell', `cell-${cell.kind}`, { selected: isSelected(cell) }]"
              @pointerdown="startSelection($event, cell)"
              @pointerenter="dragInto(cell)"
              @pointerup="stopDragging"
            >
              <span v-for="(line, lineIndex) in cellText(cell).split('\n')" :key="lineIndex" v-html="renderPhysicsNotation(line)" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="cell-inspector">
      <div><strong>{{ selectedCells.length > 1 ? '批量设置' : '单元格设置' }}</strong><span>{{ selectionLabel }} · {{ selectedCells.length }} 格</span></div>
      <template v-if="selectedCell">
        <label>用途<select :value="selectedKind" @change="updateSelectedKind(($event.target as HTMLSelectElement).value as 'label' | 'field')"><option v-if="!selectedKind" value="" disabled>用途不一致</option><option value="label">标题或说明</option><option value="field">数据输入</option></select></label>
        <PhysicsNotationInput v-if="selectedKind === 'label' && selectedCells.length === 1" :model-value="selectedCell.text" label="显示文字" @update:model-value="updateSelectedText($event || '')" />
        <div v-else-if="selectedKind === 'label'" class="bulk-text-control"><PhysicsNotationInput v-model="batchText" label="统一显示文字" placeholder="输入后应用到所选单元格" /><button class="bulk-apply-button" type="button" @click="updateSelectedText(batchText)">应用</button></div>
        <label v-else-if="selectedKind === 'field'">所选格记录的测量项<select :value="selectedCells.every((cell) => cell.fieldKey === selectedCell?.fieldKey) ? selectedCell?.fieldKey : ''" @change="updateSelectedField(($event.target as HTMLSelectElement).value)"><option value="">请选择</option><option v-for="field in table.fields" :key="field.key" :value="field.key">{{ field.label }} · {{ field.symbol || '未设符号' }} / {{ field.unit }}</option></select></label>
      </template>
      <p v-else>选择单元格后，设置显示文字或要记录的测量项。原表格支持鼠标拖选，增强表格还支持方向键和 Shift 扩选。</p>
    </div>
  </div>
</template>
