import { expect, test } from '@playwright/test'

test('demo teacher session persists across pages and ends on sign-out', async ({ page, context }) => {
  await page.goto('/login')
  await page.getByLabel('账号').fill('t0001')
  await page.getByLabel('密码').fill('123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/teacher$/)
  const sessionCookie = (await context.cookies()).find((cookie) => cookie.name === 'labmate_session')
  expect(sessionCookie).toBeDefined()

  await page.reload()
  await expect(page).toHaveURL(/\/teacher$/)
  const reopenedPage = await context.newPage()
  await reopenedPage.goto('/login')
  await expect(reopenedPage).toHaveURL(/\/teacher$/)
  await reopenedPage.close()

  await page.goto('/student')
  await expect(page).toHaveURL(/\/teacher$/)
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page).toHaveURL(/\/login$/)

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: '登录 LabMate' })).toBeVisible()
  await expect(page.getByLabel('账号')).toHaveAttribute('autocomplete', 'username')
  await expect(page.getByLabel('密码')).toHaveAttribute('autocomplete', 'current-password')
})
