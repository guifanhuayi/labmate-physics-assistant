import { describe, expect, it } from 'vitest'
import {
  applySymbolShortcut,
  createMechanicsTemplate,
  createSpreadsheetGrid,
  mergeSpreadsheetCells,
  schemaValueOptions,
  splitSpreadsheetCell,
} from '../src/templates/designer'

describe('mechanics experiment template preset', () => {
  it('turns the report tables into four mobile-friendly data blocks', () => {
    const schema = createMechanicsTemplate()

    expect(schema.title).toBe('力学综合实验')
    expect(schema.steps).toHaveLength(5)
    expect(schema.preparationQuestions).toHaveLength(5)
    expect(schema.discussionQuestions).toHaveLength(5)
    expect(schema.tables.map((table) => table.id)).toEqual([
      'amplitude_periods',
      'mass_periods',
      'damped_speeds',
      'peak_decay',
    ])
    expect(schema.tables.find((table) => table.id === 'damped_speeds')?.minimumRows).toBe(30)
  })

  it('keeps every field and calculation key unique and makes chart axes selectable', () => {
    const schema = createMechanicsTemplate()
    const keys = schemaValueOptions(schema).map((item) => item.key)

    expect(new Set(keys).size).toBe(keys.length)
    for (const chart of schema.charts) {
      expect(keys).toContain(chart.x)
      expect(keys).toContain(chart.y)
    }
  })

  it('merges and splits spreadsheet header cells without allowing data cells to merge', () => {
    const schema = createMechanicsTemplate()
    const fields = schema.tables[0].fields
    const grid = createSpreadsheetGrid(fields, 3)
    const merged = mergeSpreadsheetCells(grid, { startRow: 0, endRow: 0, startColumn: 0, endColumn: 2 })

    expect(merged.cells.find((cell) => cell.row === 0 && cell.column === 0)?.colSpan).toBe(3)
    expect(splitSpreadsheetCell(merged, 0, 0, fields).cells.filter((cell) => cell.row === 0)).toHaveLength(fields.length)
    expect(() => mergeSpreadsheetCells(grid, { startRow: 1, endRow: 1, startColumn: 0, endColumn: 1 })).toThrow('数据输入单元格不能合并')
  })

  it('stores column widths, frozen rows, field ownership and symbol shortcuts', () => {
    const schema = createMechanicsTemplate()
    const grid = createSpreadsheetGrid(schema.tables[0].fields, 3)

    expect(grid.columnWidths).toEqual(schema.tables[0].fields.map(() => 140))
    expect(grid.frozenRows).toBe(1)
    expect(schema.tables[0].fields.every((field) => field.scope === 'individual')).toBe(true)
    expect(applySymbolShortcut('Delta x_1^2')).toBe('Δx₁²')
  })
})
