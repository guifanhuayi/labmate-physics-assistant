import { describe, expect, it } from 'vitest'
import { createMechanicsTemplate, ensureTableGrid, mergeSpreadsheetCells } from '../src/templates/designer'
import { applyLabelEdits, labelEditsFromUniver, parseClipboardText, pasteTableText, tableToUniverWorkbook } from '../src/templates/univerAdapter'

describe('LabMate / Univer template boundary', () => {
  it('projects headers, merges, widths and frozen rows without turning text into formulas', () => {
    const table = ensureTableGrid(structuredClone(createMechanicsTemplate().tables[0]))
    table.grid!.columnWidths[0] = 180
    table.grid = mergeSpreadsheetCells(table.grid!, { startRow: 0, endRow: 0, startColumn: 0, endColumn: 1 })
    table.grid.cells.find(cell => cell.row === 0 && cell.column === 0)!.text = '=SUM(A1:A2)'
    const sheet = tableToUniverWorkbook(table, 'preview').sheets![table.id]
    expect(sheet.cellData![0][0]).toMatchObject({ v: '=SUM(A1:A2)', t: 2 })
    expect(sheet.cellData![0][0].f).toBeUndefined()
    expect(sheet.mergeData).toEqual([{ startRow: 0, endRow: 0, startColumn: 0, endColumn: 1 }])
    expect(sheet.columnData![0].w).toBe(180)
    expect(sheet.freeze!.ySplit).toBe(1)
    expect(sheet.cellData![1][0].v).toContain('学生输入')
  })

  it('keeps all field identities, units and sharing metadata when changing headers', () => {
    const table = ensureTableGrid(createMechanicsTemplate().tables[0])
    const before = JSON.stringify(table)
    const updated = applyLabelEdits(table, [{ row: 0, column: 0, text: '振幅 Δx' }])
    expect(updated.fields).toEqual(table.fields)
    expect(updated.grid!.cells.filter(cell => cell.kind === 'field')).toEqual(table.grid!.cells.filter(cell => cell.kind === 'field'))
    expect(updated.grid!.cells[0].text).toBe('振幅 Δx')
    expect(JSON.stringify(table)).toBe(before)
  })

  it('rejects a whole paste when any destination is a bound input or beyond the sheet', () => {
    const table = ensureTableGrid(createMechanicsTemplate().tables[0])
    const before = JSON.stringify(table)
    expect(() => pasteTableText(table, { startRow: 0, endRow: 0, startColumn: 0, endColumn: 0 }, '表头\n覆盖输入')).toThrow('测量项绑定')
    expect(() => pasteTableText(table, { startRow: 0, endRow: 0, startColumn: 3, endColumn: 3 }, '甲\t乙')).toThrow('超出')
    expect(JSON.stringify(table)).toBe(before)
  })

  it('handles Excel quoted tabs and multiline cells while preserving formula-like text as text', () => {
    expect(parseClipboardText('"名称\t单位"\t"第一行\n第二行"\r\n"A""B"\t=1+2\r\n'))
      .toEqual([['名称\t单位', '第一行\n第二行'], ['A"B', '=1+2']])
    const table = ensureTableGrid(createMechanicsTemplate().tables[0])
    const updated = pasteTableText(table, { startRow: 0, endRow: 0, startColumn: 0, endColumn: 0 }, '=SUM(A1)\tΔt')
    expect(updated.grid!.cells[0].text).toBe('=SUM(A1)')
  })

  it('refuses native formulas and merged interiors instead of guessing a binding', () => {
    const table = ensureTableGrid(createMechanicsTemplate().tables[0])
    expect(() => labelEditsFromUniver(table, { 0: { 0: { f: '=1+2' } } })).toThrow('不执行')
    expect(() => labelEditsFromUniver(table, { 0: { 0: { s: { bl: 1 } } } })).toThrow('不会更改标题')
    expect(labelEditsFromUniver(table, { 0: { 0: { p: { id: 'text', documentStyle: {}, body: { dataStream: '读数\r\n' } } } } }))
      .toEqual([{ row: 0, column: 0, text: '读数' }])
    table.grid = mergeSpreadsheetCells(table.grid!, { startRow: 0, endRow: 0, startColumn: 0, endColumn: 1 })
    expect(() => applyLabelEdits(table, [{ row: 0, column: 1, text: '内部' }])).toThrow('合并')
  })
})
