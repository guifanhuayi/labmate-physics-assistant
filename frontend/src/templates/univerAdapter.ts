import type { ICellData, IObjectMatrixPrimitiveType, IWorkbookData, IWorksheetData, Nullable } from '@univerjs/core'
import { cellAt, createSpreadsheetGrid, type CellRange, type TemplateTable } from './designer'

export interface LabelEdit { row: number; column: number; text: string }

export function tableGrid(table: TemplateTable) {
  return table.grid || createSpreadsheetGrid(table.fields, table.minimumRows)
}

/** Only the canvas projection uses Univer's model. Field metadata stays in LabMate. */
export function tableToUniverWorkbook(table: TemplateTable, workbookId: string): Partial<IWorkbookData> {
  const grid = tableGrid(table)
  const cellData: IWorksheetData['cellData'] = {}
  for (const cell of grid.cells) {
    const field = table.fields.find(item => item.key === cell.fieldKey)
    const text = cell.kind === 'label' ? cell.text
      : `${field?.label || '未绑定测量项'}\n${field?.symbol || ''}${field?.unit ? ` / ${field.unit}` : ''}\n〔学生输入〕`
    cellData[cell.row] ||= {}
    cellData[cell.row][cell.column] = {
      v: text, t: 2, // Force text: a teacher's '=...' is never an executable formula.
      s: { bg: { rgb: cell.kind === 'label' ? '#e7eff8' : '#f3faf6' }, cl: { rgb: '#234b69' },
        fs: 12, ht: 2, vt: 2, tb: 3, bl: cell.kind === 'label' ? 1 : 0 },
    }
  }
  const sheet: IWorksheetData = {
    id: table.id, name: table.title || '实验数据表', tabColor: '#176c62', hidden: 0,
    rowCount: grid.rows, columnCount: grid.columns,
    freeze: { xSplit: 0, ySplit: grid.frozenRows, startRow: grid.frozenRows || -1, startColumn: -1 },
    zoomRatio: 1, scrollTop: 0, scrollLeft: 0, defaultColumnWidth: 140, defaultRowHeight: 64,
    mergeData: grid.cells.filter(cell => cell.rowSpan > 1 || cell.colSpan > 1).map(cell => ({
      startRow: cell.row, endRow: cell.row + cell.rowSpan - 1,
      startColumn: cell.column, endColumn: cell.column + cell.colSpan - 1,
    })),
    cellData, rowData: {}, columnData: Object.fromEntries(grid.columnWidths.map((w, index) => [index, { w }])),
    rowHeader: { width: 42 }, columnHeader: { height: 28 }, showGridlines: 1, rightToLeft: 0,
  }
  return { id: workbookId, name: table.title, appVersion: '1.2.0', locale: 'zhCN' as IWorkbookData['locale'],
    sheetOrder: [table.id], sheets: { [table.id]: sheet }, styles: {} }
}

export function applyLabelEdits(table: TemplateTable, edits: LabelEdit[]): TemplateTable {
  const grid = tableGrid(table)
  const replacements = new Map<string, string>()
  for (const edit of edits) {
    if (!Number.isInteger(edit.row) || !Number.isInteger(edit.column)) throw new Error('单元格位置无效。')
    const cell = cellAt(grid, edit.row, edit.column)
    if (!cell) throw new Error('粘贴范围超出当前表格，请先增加行列。')
    if (cell.kind !== 'label') throw new Error('输入格保留测量项绑定。请先在下方将目标格的用途设为“标题或说明”。')
    if (cell.row !== edit.row || cell.column !== edit.column) throw new Error('粘贴范围穿过合并单元格，请先拆分。')
    if (edit.text.length > 4000) throw new Error('每个标题或说明最多可输入 4000 个字符。')
    replacements.set(cell.id, edit.text)
  }
  return { ...table, grid: { ...grid, cells: grid.cells.map(cell => replacements.has(cell.id)
    ? { ...cell, text: replacements.get(cell.id)! } : cell) } }
}

/** Validate an entire native edit before allowing Univer to mutate its canvas. */
export function labelEditsFromUniver(table: TemplateTable, matrix: IObjectMatrixPrimitiveType<Nullable<ICellData>>): LabelEdit[] {
  const edits: LabelEdit[] = []
  for (const [row, cells] of Object.entries(matrix)) {
    for (const [column, raw] of Object.entries(cells || {}) as Array<[string, Nullable<ICellData>]>) {
      const data = raw || null
      if (data?.f || data?.si) throw new Error('实验模板不执行表格公式；需要等号文字时请使用下方“显示文字”输入框。')
      if (data && !Object.hasOwn(data, 'v') && !data.p?.body) throw new Error('请使用模板工具栏设置表格；当前操作不会更改标题文字。')
      const text = data?.p?.body?.dataStream?.replace(/\r?\n$/, '') ?? String(data?.v ?? '')
      edits.push({ row: Number(row), column: Number(column), text })
    }
  }
  applyLabelEdits(table, edits)
  return edits
}

/** Excel-compatible TSV: retain quoted tabs/newlines and escaped double quotes. */
export function parseClipboardText(text: string): string[][] {
  if (text.length > 800000) throw new Error('粘贴内容过大，请分批粘贴。')
  const rows: string[][] = []
  let row: string[] = [], value = '', quoted = false
  const finishRow = () => { row.push(value); rows.push(row); row = []; value = '' }
  for (let index = 0; index < text.length; index++) {
    const character = text[index]
    if (character === '"' && (quoted || value === '')) {
      if (quoted && text[index + 1] === '"') { value += '"'; index++ }
      else quoted = !quoted
    } else if (!quoted && character === '\t') { row.push(value); value = '' }
    else if (!quoted && (character === '\n' || character === '\r')) {
      if (character === '\r' && text[index + 1] === '\n') index++
      finishRow()
    } else value += character
    if (rows.length > 201 || row.length > 30) throw new Error('粘贴内容超过 201 行或 30 列。')
  }
  if (quoted) throw new Error('粘贴内容的引号不完整，请重新复制。')
  if (value !== '' || row.length || !rows.length) finishRow()
  if (rows.length > 201 || rows.some(item => item.length > 30)) throw new Error('粘贴内容超过 201 行或 30 列。')
  return rows
}

export function pasteTableText(table: TemplateTable, selection: CellRange, text: string): TemplateTable {
  const rows = parseClipboardText(text)
  return applyLabelEdits(table, rows.flatMap((values, row) => values.map((value, column) => ({
    row: selection.startRow + row, column: selection.startColumn + column, text: value,
  }))))
}
