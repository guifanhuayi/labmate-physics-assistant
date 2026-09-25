import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TemplateDesigner from '../src/components/TemplateDesigner.vue'
import { managementApi } from '../src/api/client'
import { createBlankTemplate } from '../src/templates/designer'

describe('saved template interactions', () => {
  afterEach(() => vi.restoreAllMocks())

  it('opens a saved template from the reactive sidebar list', async () => {
    const schema = createBlankTemplate()
    schema.title = '已保存的光学实验'
    const wrapper = mount(TemplateDesigner, {
      props: {
        templates: [{
          id: 'template-1', name: '已保存的光学实验', description: '观察光路',
          status: 'draft', schema: schema as unknown as Record<string, unknown>,
          versionCount: 0, latestVersionId: null,
        }],
      },
      global: { stubs: { SpreadsheetTableEditor: true } },
    })

    await wrapper.get('.template-list-button').trigger('click')

    expect((wrapper.get('input[required]').element as HTMLInputElement).value).toBe('已保存的光学实验')
    expect(wrapper.text()).toContain('正在编辑“已保存的光学实验”')
  })

  it('removes a saved template after confirmation', async () => {
    const remove = vi.spyOn(managementApi, 'deleteTemplate').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(TemplateDesigner, {
      props: { templates: [{ id: 'template-2', name: '旧模板', description: '', status: 'draft', schema: {}, versionCount: 0, latestVersionId: null }] },
      global: { stubs: { SpreadsheetTableEditor: true } },
    })

    await wrapper.get('[aria-label="删除模板 旧模板"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('template-2')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.text()).toContain('旧模板”已从列表移除')
  })

  it('converts a Word upload into an unsaved editable draft with review warnings', async () => {
    const schema = createBlankTemplate()
    schema.title = '导入后的实验'
    const upload = vi.spyOn(managementApi, 'importWordTemplate').mockResolvedValue({ schema: schema as unknown as Record<string, unknown>, warnings: ['请核对字段单位。'] })
    const wrapper = mount(TemplateDesigner, {
      props: { templates: [] }, global: { stubs: { SpreadsheetTableEditor: true } },
    })
    const input = wrapper.get('#word-template-file')
    const file = new File(['test'], 'experiment.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(upload).toHaveBeenCalledWith(file)
    expect((wrapper.get('input[required]').element as HTMLInputElement).value).toBe('导入后的实验')
    expect(wrapper.text()).toContain('请核对字段单位。')
    expect(wrapper.text()).toContain('生成可编辑草稿')
  })

  it('adds Excel sheets to the current draft without replacing its existing tables', async () => {
    const imported = createBlankTemplate()
    imported.tables[0].title = 'Excel 原表'
    const upload = vi.spyOn(managementApi, 'importExcelTemplate').mockResolvedValue({
      schema: imported as unknown as Record<string, unknown>, warnings: ['请核对录入类型。'],
    })
    const wrapper = mount(TemplateDesigner, {
      props: { templates: [] }, global: { stubs: { SpreadsheetTableEditor: true } },
    })
    const input = wrapper.get('#excel-template-file')
    const file = new File(['test'], 'record.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(upload).toHaveBeenCalledWith(file)
    expect(wrapper.findAll('.table-editor')).toHaveLength(5)
    expect(wrapper.text()).toContain('Excel 原表')
    expect(wrapper.text()).toContain('请核对录入类型。')
  })

  it('creates a table with chosen data rows and named measurement columns', async () => {
    const wrapper = mount(TemplateDesigner, {
      props: { templates: [] }, global: { stubs: { SpreadsheetTableEditor: true } },
    })

    await wrapper.get('[aria-label="新表格数据行数"]').setValue('5')
    await wrapper.get('[aria-label="新表格测量列数"]').setValue('3')
    await wrapper.get('button.add-table-button').trigger('click')

    const table = wrapper.findAll('.table-editor').at(-1)!
    expect(table.findAll('[aria-label="测量名称"]')).toHaveLength(3)
    expect(table.findAll('[aria-label="测量符号"]')).toHaveLength(3)
    expect(table.text()).toContain('5 行')
    expect(table.text()).toContain('3 列')
  })

  it('updates the visible table header when a measurement name changes', async () => {
    const wrapper = mount(TemplateDesigner, { props: { templates: [] } })
    await wrapper.findAll('.preset-card').find((button) => button.text().includes('空白实验'))!.trigger('click')
    const table = wrapper.get('.table-editor')

    await table.get('[aria-label="测量名称"]').setValue('电压')

    expect(table.get('.sheet-canvas tr:first-child td').text()).toContain('电压')
  })
})
