import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SpreadsheetTableEditor from '../src/components/SpreadsheetTableEditor.vue'
import { createBlankTemplate, createMeasurementField, createSpreadsheetGrid, type TemplateTable } from '../src/templates/designer'

describe('teacher table sizing', () => {
  it('accepts a preset row count in the mounted editor', async () => {
    const table = createBlankTemplate().tables[0]
    const wrapper = mount(SpreadsheetTableEditor, { props: { modelValue: table } })

    await wrapper.get('input[type="number"]').setValue('8')

    const updates = wrapper.emitted('update:modelValue') as TemplateTable[][] | undefined
    expect(updates?.at(-1)?.[0].grid?.rows).toBe(9)
    expect(updates?.at(-1)?.[0].minimumRows).toBe(8)
  })

  it('adds a named measurement for each new column and restores the prior layout on undo', async () => {
    const wrapper = mount(SpreadsheetTableEditor, { props: { modelValue: createBlankTemplate().tables[0] } })

    await wrapper.findAll('input[type="number"]')[1].setValue('3')
    const updates = wrapper.emitted('update:modelValue') as TemplateTable[][]
    const expanded = updates.at(-1)![0]
    expect(expanded.grid?.columns).toBe(3)
    expect(expanded.fields.map((item) => item.label)).toEqual(['测量值', '测量数据 2', '测量数据 3'])
    await wrapper.setProps({ modelValue: expanded })
    await wrapper.findAll('button').find((button) => button.text() === '撤销')!.trigger('click')
    const restored = updates.at(-1)![0]
    expect(restored.grid?.columns).toBe(1)
    expect(restored.fields).toHaveLength(1)
  })

  it('selects a rectangle by left-button drag and applies purpose and text to every cell', async () => {
    const table = createBlankTemplate().tables[0]
    const fields = [...table.fields]
    fields.push(createMeasurementField(table.id, 1, fields))
    fields.push(createMeasurementField(table.id, 2, fields))
    table.fields = fields
    table.grid = createSpreadsheetGrid(fields, 2)
    table.minimumRows = 2
    table.maximumRows = 2
    const wrapper = mount(SpreadsheetTableEditor, { props: { modelValue: table } })
    const cells = wrapper.findAll('.sheet-cell')

    await cells[3].trigger('pointerdown', { button: 0 })
    await cells[5].trigger('pointerenter')
    await cells[5].trigger('pointerup')
    expect(wrapper.get('.cell-inspector').text()).toContain('3 格')
    await wrapper.get('.cell-inspector select').setValue('label')
    expect(table.grid.cells.filter((cell) => cell.row === 1).every((cell) => cell.kind === 'label')).toBe(true)

    await wrapper.get('.bulk-text-control input').setValue('统一说明 Δx')
    await wrapper.get('.bulk-apply-button').trigger('click')
    expect(table.grid.cells.filter((cell) => cell.row === 1).map((cell) => cell.text)).toEqual(['统一说明 Δx', '统一说明 Δx', '统一说明 Δx'])
  })
})
