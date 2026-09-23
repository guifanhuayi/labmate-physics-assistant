<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  cellAt,
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
const undoStack = ref<SpreadsheetGrid[]>([])
const redoStack = ref<SpreadsheetGrid[]>([])

const grid = computed(() => {
  if (!table.value.grid) table.value.grid = createSpreadsheetGrid(table.value.fields, table.value.minimumRows)
  return table.value.grid
})

const selectedCell = computed(() => selection.value
  ? cellAt(grid.value, selection.value.startRow, selection.value.startColumn) || null
  : null)

const selectionLabel = computed(() => {
  if (!selection.value) return '尚未选择单元格'
  const start = `R${selection.value.startRow + 1}C${selection.value.startColumn + 1}`
  const end = `R${selection.value.endRow + 1}C${selection.value.endColumn + 1}`
  return start === end ? start : `${start}:${end}`
})

const selectedColumnWidth = computed(() => selectedCell.value ? grid.value.columnWidths[selectedCell.value.column] : 140)

function rememberGrid() {
  undoStack.value.push(structuredClone(grid.value))
  if (undoStack.value.length > 30) undoStack.value.shift()
  redoStack.value = []
}

function undo() {
  const previous = undoStack.value.pop()
  if (!previous) return
  redoStack.value.push(structuredClone(grid.value))
  table.value.grid = previous
  selection.value = null
}

function redo() {
  const next = redoStack.value.pop()
  if (!next) return
  undoStack.value.push(structuredClone(grid.value))
  table.value.grid = next
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

function selectCell(cell: SpreadsheetCell) {
  localError.value = ''
  if (!selection.value || selection.value.startRow !== selection.value.endRow || selection.value.startColumn !== selection.value.endColumn) {
    selection.value = { startRow: cell.row, endRow: cell.row + cell.rowSpan - 1, startColumn: cell.column, endColumn: cell.column + cell.colSpan - 1 }
    return
  }
  selection.value = {
    ...selection.value,
    endRow: cell.row + cell.rowSpan - 1,
    endColumn: cell.column + cell.colSpan - 1,
  }
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
  const nextRows = Math.max(2, Math.min(201, rows))
  const nextColumns = Math.max(1, Math.min(30, columns))
  rememberGrid()
  table.value.grid = resizeSpreadsheetGrid(grid.value, nextRows, nextColumns, table.value.fields)
  const dataRows = nextRows - 1
  table.value.minimumRows = dataRows
  table.value.maximumRows = dataRows
  selection.value = null
  localError.value = ''
}

function updateSelectedText(value: string) {
  if (selectedCell.value && selectedCell.value.text !== value) {
    rememberGrid()
    selectedCell.value.text = value
  }
}

function updateSelectedKind(value: 'label' | 'field') {
  if (!selectedCell.value) return
  rememberGrid()
  selectedCell.value.kind = value
  if (value === 'field') {
    selectedCell.value.fieldKey = selectedCell.value.fieldKey || table.value.fields[0]?.key
    selectedCell.value.text = ''
  } else {
    delete selectedCell.value.fieldKey
  }
}

function updateSelectedField(value: string) {
  if (selectedCell.value && selectedCell.value.fieldKey !== value) {
    rememberGrid()
    selectedCell.value.fieldKey = value
  }
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
  return field ? `${field.label}\n${field.symbol || field.key} / ${field.unit}` : '未绑定字段'
}
</script>

<template>
  <div class="spreadsheet-editor">
    <div class="spreadsheet-toolbar">
      <div class="sheet-size-controls">
        <label>总行数<input :value="grid.rows" type="number" min="2" max="201" @change="resize(Number(($event.target as HTMLInputElement).value), grid.columns)" /></label>
        <label>总列数<input :value="grid.columns" type="number" min="1" max="30" @change="resize(grid.rows, Number(($event.target as HTMLInputElement).value))" /></label>
      </div>
      <div class="sheet-actions">
        <button type="button" :disabled="!undoStack.length" @click="undo">撤销</button>
        <button type="button" :disabled="!redoStack.length" @click="redo">重做</button>
        <button type="button" @click="resize(grid.rows + 1, grid.columns)">＋ 行</button>
        <button type="button" :disabled="grid.rows <= 2" @click="resize(grid.rows - 1, grid.columns)">－ 行</button>
        <button type="button" @click="resize(grid.rows, grid.columns + 1)">＋ 列</button>
        <button type="button" :disabled="grid.columns <= 1" @click="resize(grid.rows, grid.columns - 1)">－ 列</button>
        <button type="button" :disabled="!selection" @click="mergeSelection">合并选区</button>
        <button type="button" :disabled="!selectedCell || (selectedCell.rowSpan === 1 && selectedCell.colSpan === 1)" @click="splitSelection">拆分单元格</button>
      </div>
    </div>
    <div class="sheet-layout-controls">
      <label>冻结顶部行数<input :value="grid.frozenRows" type="number" min="0" :max="grid.rows" @change="updateFrozenRows(Number(($event.target as HTMLInputElement).value))" /></label>
      <label>所选列宽<input :value="selectedColumnWidth" type="range" min="80" max="320" step="10" :disabled="!selectedCell" @change="updateColumnWidth(Number(($event.target as HTMLInputElement).value))" /></label>
    </div>
    <p class="sheet-help">第一次点击选择起点，第二次点击确定矩形终点；数据输入格不能合并。</p>
    <p v-if="localError" class="sheet-error">{{ localError }}</p>
    <div class="sheet-canvas">
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
              @click="selectCell(cell)"
            >
              <span v-for="line in cellText(cell).split('\n')" :key="line">{{ line }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="cell-inspector">
      <div><strong>单元格设置</strong><span>{{ selectionLabel }}</span></div>
      <template v-if="selectedCell">
        <label>用途<select :value="selectedCell.kind" @change="updateSelectedKind(($event.target as HTMLSelectElement).value as 'label' | 'field')"><option value="label">标题或说明</option><option value="field">数据输入</option></select></label>
        <label v-if="selectedCell.kind === 'label'">显示文字<input :value="selectedCell.text" @input="updateSelectedText(($event.target as HTMLInputElement).value)" /></label>
        <label v-else>绑定记录字段<select :value="selectedCell.fieldKey" @change="updateSelectedField(($event.target as HTMLSelectElement).value)"><option value="">请选择</option><option v-for="field in table.fields" :key="field.key" :value="field.key">{{ field.label }} · {{ field.symbol || field.key }} / {{ field.unit }}</option></select></label>
      </template>
      <p v-else>点击表格中的单元格后，可设置其内容或绑定数据字段。</p>
    </div>
  </div>
</template>
