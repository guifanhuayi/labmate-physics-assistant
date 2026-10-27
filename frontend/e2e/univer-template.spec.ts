import { expect, test, type Locator, type Page } from '@playwright/test'
import type { TemplateSchema } from '../src/templates/designer'

test.afterEach(async ({ page }, info) => {
  await page.screenshot({ path: info.outputPath('page.png') })
})

async function openDesigner(page: Page) {
  const saved: Array<{ schema: TemplateSchema }> = []
  const loadedChunks: string[] = []
  page.on('request', request => { if (request.url().includes('UniverTableCanvas')) loadedChunks.push(request.url()) })
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    let body: unknown = []
    if (url.pathname === '/api/auth/mode') body = { demoEnabled: true, demoAccounts: {} }
    if (url.pathname === '/api/auth/me') body = { id: 'teacher', role: 'teacher', account: 't0001', name: '演示教师', enrollmentCompleted: true }
    if (url.pathname === '/api/templates' && request.method() === 'POST') body = { id: 'template-test' }
    if (url.pathname === '/api/templates/template-test/draft' && request.method() === 'PUT') {
      saved.push(request.postDataJSON())
      body = { id: 'template-test' }
    }
    if (url.pathname.endsWith('/validate')) body = { valid: true, issues: [] }
    if (url.pathname.endsWith('/publish')) body = { id: 'version-test', versionNumber: 1 }
    await route.fulfill({ json: body })
  })
  await page.goto('/teacher')
  await page.getByRole('button', { name: '实验模板', exact: true }).click()
  const editor = page.locator('.spreadsheet-editor').first()
  expect(loadedChunks).toHaveLength(0)
  await editor.getByRole('button', { name: '增强表格', exact: true }).click()
  await expect(editor.locator('.univer-canvas-host canvas:visible').first()).toBeVisible({ timeout: 15000 })
  await editor.locator('.univer-canvas-host').screenshot({ path: test.info().outputPath('initial-canvas.png') })
  return { editor, saved }
}

async function clickCell(page: Page, editor: Locator, row: number, column: number, double = false) {
  const host = editor.locator('.univer-canvas-host')
  await host.scrollIntoViewIfNeeded()
  const rect = (await host.boundingBox())!
  const position = { x: rect.x + 42 + column * 140 + 65, y: rect.y + 28 + row * 64 + 28 }
  if (double) await page.mouse.dblclick(position.x, position.y)
  else await page.mouse.click(position.x, position.y)
}

test('Univer edits and LabMate paste share the original schema, history and immutable publish path', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const { editor, saved } = await openDesigner(page)
  await clickCell(page, editor, 0, 0, true)
  await expect(editor.getByRole('dialog', { name: '编辑标题或说明' })).toBeVisible()
  await editor.getByLabel('标题或说明文字', { exact: true }).fill('Amplitude header')
  await expect(editor.getByRole('dialog', { name: '编辑标题或说明' })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('integration-preview.png') })
  // Save while the native cell editor still has focus: flush must commit it first.
  await page.getByRole('button', { name: '保存并检查', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('通过发布校验')
  expect(saved.at(-1)?.schema.tables[0].grid!.cells[0].text).toBe('Amplitude header')
  const fieldKeys = saved.at(-1)!.schema.tables[0].fields.map((field: { key: string }) => field.key)

  await editor.getByRole('button', { name: '原表格', exact: true }).click()
  await expect(editor.locator('.sheet-cell').first()).toContainText('Amplitude header')
  await editor.locator('.sheet-cell').first().click()
  await editor.getByRole('button', { name: '粘贴表格文字', exact: true }).click()
  await editor.getByLabel('待粘贴的表格文字').fill('=SUM(A1)\t周期 Δt')
  await editor.getByRole('button', { name: '应用粘贴', exact: true }).click()
  await expect(editor.locator('.sheet-cell').first()).toContainText('=SUM(A1)')
  await expect(editor.locator('.sheet-cell').nth(1)).toContainText('周期 Δt')
  await editor.getByRole('button', { name: '增强表格', exact: true }).click()
  await expect(editor.locator('.univer-canvas-host canvas:visible').first()).toBeVisible()
  await clickCell(page, editor, 0, 0)
  await page.keyboard.press('Shift+ArrowRight')
  await expect(editor.locator('.cell-inspector')).toContainText('2 格')
  await editor.getByRole('button', { name: '合并选区', exact: true }).click()
  await editor.getByRole('button', { name: '原表格', exact: true }).click()
  await expect(editor.locator('.sheet-cell').first()).toHaveAttribute('colspan', '2')
  await editor.getByRole('button', { name: '撤销', exact: true }).click()
  await expect(editor.locator('.sheet-cell').first()).toHaveAttribute('colspan', '1')

  await page.getByRole('button', { name: '发布新版本', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已选中刚发布的模板版本')
  expect(saved.at(-1)!.schema.tables[0].fields.map((field: { key: string }) => field.key)).toEqual(fieldKeys)
  expect(saved.at(-1)!.schema.tables[0].grid!.cells[0].text).toBe('=SUM(A1)')
  expect(errors).toEqual([])
})

test('bound cells reject edits and partial paste; mobile can return to the original editor', async ({ page }) => {
  const { editor } = await openDesigner(page)
  await clickCell(page, editor, 1, 0, true)
  await expect(editor.locator('.sheet-error')).toContainText('用于学生录入')
  await editor.getByRole('button', { name: '原表格', exact: true }).click()
  const originalHeader = await editor.locator('.sheet-cell').first().textContent()
  await editor.locator('.sheet-cell').first().click()
  await editor.getByRole('button', { name: '粘贴表格文字', exact: true }).click()
  await editor.getByLabel('待粘贴的表格文字').fill('不应保存的表头\n覆盖输入格')
  await editor.getByRole('button', { name: '应用粘贴', exact: true }).click()
  await expect(editor.locator('.sheet-error')).toContainText('测量项绑定')
  expect(await editor.locator('.sheet-cell').first().textContent()).toBe(originalHeader)
  await page.setViewportSize({ width: 390, height: 844 })
  await editor.scrollIntoViewIfNeeded()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
})

test('native clipboard paste and keyboard undo return through the shared LabMate history', async ({ page, context }) => {
  const { editor } = await openDesigner(page)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.evaluate(() => navigator.clipboard.writeText('粘贴表头\t=1+2'))
  await clickCell(page, editor, 0, 0)
  await page.keyboard.press('ControlOrMeta+V')
  await expect(editor.getByRole('button', { name: '撤销', exact: true })).toBeEnabled()
  await editor.getByRole('button', { name: '原表格', exact: true }).click()
  await expect(editor.locator('.sheet-cell').first()).toContainText('粘贴表头')
  await expect(editor.locator('.sheet-cell').nth(1)).toContainText('=1+2')
  await editor.getByRole('button', { name: '增强表格', exact: true }).click()
  await expect(editor.locator('.univer-canvas-host canvas:visible').first()).toBeVisible()
  await clickCell(page, editor, 0, 0)
  await page.keyboard.press('ControlOrMeta+Z')
  await editor.getByRole('button', { name: '原表格', exact: true }).click()
  await expect(editor.locator('.sheet-cell').first()).toContainText('振幅')
  await expect(editor.locator('.sheet-cell').nth(1)).toContainText('周期第 1 次')
})
