import { expect, test } from '@playwright/test'

test('demo login accepts an imported student number with any nonempty password and rejects unknown numbers', async ({ page }) => {
  await page.route('**/api/auth/mode', (route) => route.fulfill({ json: {
    demoEnabled: true, demoAccounts: { student: '', teacher: 't0001', admin: 'admin' },
  } }))
  await page.route('**/api/auth/me', (route) => route.fulfill({ status: 401, json: {
    error: { code: 'unauthenticated', message: '请先登录。' },
  } }))
  await page.route('**/api/auth/login', (route) => {
    const { account, password } = route.request().postDataJSON()
    if (account === '20260022' && password === 'letters!') return route.fulfill({ json: {
      id: '11111111-1111-4111-8111-111111111111', account, name: '名单学生', role: 'student',
      mustChangePassword: false, enrollmentCompleted: false, phoneMasked: null,
    } })
    return route.fulfill({ status: 401, json: {
      error: { code: 'invalid_demo_credentials', message: '账号不存在、未导入班级名单或已停用。' },
    } })
  })
  await page.route('**/api/student/assignments', (route) => route.fulfill({ json: [] }))

  await page.goto('/login')
  await page.getByLabel('账号').fill('99999999')
  await page.getByLabel('密码').fill('anything')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('未导入班级名单')

  await page.getByLabel('账号').fill('20260022')
  await page.getByLabel('密码').fill('letters!')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/student$/)
  await expect(page.getByRole('heading', { name: '我的实验任务' })).toBeVisible()
})
