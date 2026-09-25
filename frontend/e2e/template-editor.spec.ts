import { expect, test } from '@playwright/test'

test('teacher toolbar stays visible while scrolling and cells select by dragging', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('账号').fill('t0001')
  await page.getByLabel('密码').fill('123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '实验模板' }).click()

  const toolbar = page.locator('.designer-toolbar')
  await expect(toolbar.getByRole('button', { name: '保存并检查' })).toBeVisible()
  await expect(toolbar.getByRole('button', { name: '发布新版本' })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 1200))
  await expect(toolbar).toBeVisible()
  const position = await toolbar.evaluate((element) => ({
    top: element.getBoundingClientRect().top,
    style: getComputedStyle(element).position,
  }))
  expect(position.style).toBe('sticky')
  expect(position.top).toBeGreaterThanOrEqual(71)
  expect(position.top).toBeLessThan(85)

  const cells = page.locator('.table-editor').first().locator('.sheet-cell')
  await cells.first().scrollIntoViewIfNeeded()
  const start = await cells.nth(0).boundingBox()
  const end = await cells.nth(1).boundingBox()
  expect(start).not.toBeNull()
  expect(end).not.toBeNull()
  await page.mouse.move(start!.x + start!.width / 2, start!.y + start!.height / 2)
  await page.mouse.down()
  await page.mouse.move(end!.x + end!.width / 2, end!.y + end!.height / 2, { steps: 6 })
  await page.mouse.up()
  await expect(page.locator('.table-editor').first().locator('.cell-inspector')).toContainText('2 格')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.evaluate(() => window.scrollTo(0, 1200))
  await expect(toolbar.getByRole('button', { name: '保存并检查' })).toBeVisible()
  await expect(toolbar.getByRole('button', { name: '发布新版本' })).toBeVisible()
  const mobile = await page.evaluate(() => ({
    toolbarTop: document.querySelector('.designer-toolbar')!.getBoundingClientRect().top,
    headerBottom: document.querySelector('.workspace-header')!.getBoundingClientRect().bottom,
  }))
  expect(mobile.toolbarTop).toBeGreaterThanOrEqual(mobile.headerBottom - 2)
})
