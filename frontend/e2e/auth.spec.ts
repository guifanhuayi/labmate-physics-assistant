import { expect, test } from '@playwright/test'

test('student signs in once, returns without signing in again, and signs out', async ({ page, context }) => {
  await page.goto('/login')
  const accountInput = page.getByLabel('账号')
  const passwordInput = page.getByLabel('密码')
  await expect(page.getByText('演示模式已开启，任意内容均可进入。')).toBeVisible()
  await expect(accountInput).toHaveAttribute('name', 'username')
  await expect(accountInput).toHaveAttribute('autocomplete', 'username')
  await expect(passwordInput).toHaveAttribute('name', 'password')
  await expect(passwordInput).toHaveAttribute('autocomplete', 'current-password')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/student/)
  await expect(page.getByText('服务器已验证')).toBeVisible()
  const sessionCookie = (await context.cookies()).find((cookie) => cookie.name === 'labmate_session')
  expect(sessionCookie?.expires).toBeGreaterThan(Date.now() / 1000 + 29 * 24 * 60 * 60)

  await page.reload()
  await expect(page).toHaveURL(/student/)
  const reopenedPage = await context.newPage()
  await reopenedPage.goto('/login')
  await expect(reopenedPage).toHaveURL(/student/)
  await reopenedPage.close()

  await page.goto('/teacher')
  await expect(page).toHaveURL(/student/)
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page).toHaveURL(/login/)

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: '登录 LabMate' })).toBeVisible()
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
})
