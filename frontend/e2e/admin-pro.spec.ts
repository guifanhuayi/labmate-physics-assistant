import { expect, test, type Page } from '@playwright/test'

async function mockAdmin(page: Page, role = 'admin') {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = []
  const deletes: string[] = []
  let previewInvalid = false
  const classes = [{ id: 'class-1', classCode: 'PHY2401', className: '物理2401', semester: '2026秋', teacherId: 'teacher-1', teacherName: '测试教师', studentCount: 2 }]
  const teachers = [{ id: 'teacher-1', name: '测试教师', account: 't0001' }]
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/auth/mode') return route.fulfill({ json: { demoEnabled: false, demoAccounts: {} } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user', role, account: role === 'admin' ? 'admin' : '20260001', name: '测试管理员', enrollmentCompleted: true } })
    if (path === '/api/auth/logout') return route.fulfill({ status: 204 })
    if (path === '/api/teachers') return route.fulfill({ json: teachers })
    if (path === '/api/classes' && request.method() === 'GET') return route.fulfill({ json: classes })
    if (path === '/api/classes' && request.method() === 'POST') {
      const body = request.postDataJSON()
      writes.push({ path, body })
      const next = { ...body, id: 'class-2', teacherName: '测试教师', studentCount: 0 }
      classes.push(next)
      return route.fulfill({ status: 201, json: next })
    }
    if (path.endsWith('/students')) return route.fulfill({ json: [
      { id: 's1', studentNumber: '20260001', name: '名单学生甲', enrollmentCompleted: true },
      { id: 's2', studentNumber: '20260002', name: '名单学生乙', enrollmentCompleted: false },
    ] })
    if (request.method() === 'DELETE') {
      deletes.push(path)
      classes.splice(classes.findIndex(item => path.endsWith(item.id)), 1)
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/roster-imports/preview') return route.fulfill({ status: 201, json: {
      id: 'preview-1', classId: new URL(request.url()).searchParams.get('class_id'), sourceName: 'roster.csv', status: 'previewed',
      validCount: previewInvalid ? 0 : 2, errorCount: previewInvalid ? 1 : 0,
      errors: previewInvalid ? [{ row: 2, field: 'studentNumber', message: '学号不能为空' }] : [],
    } })
    if (path === '/api/roster-imports/preview-1/commit') {
      writes.push({ path, body: {} })
      return route.fulfill({ json: { id: 'preview-1', created: 2, existing: 0, membershipsAdded: 2, requiresEnrollment: 2 } })
    }
    if (path === '/api/student/assignments') return route.fulfill({ json: [] })
    return route.fulfill({ json: [] })
  })
  return { writes, deletes, invalidPreview: (value: boolean) => { previewInvalid = value } }
}

test('Ant Design Pro admin preserves class creation, roster preview/import, student lists and confirmed deletion', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const state = await mockAdmin(page)
  await page.goto('/admin')
  await expect(page.getByText('班级总数', { exact: true })).toBeVisible()
  await expect(page.getByText('教师总数', { exact: true })).toBeVisible()
  await expect(page.locator('.admin-pro-host')).toBeVisible()
  expect(await page.locator('.admin-pro-host').evaluate(host => !!host.shadowRoot?.querySelector('style[data-css-hash]'))).toBe(true)
  await page.screenshot({ path: info.outputPath('admin-overview.png') })
  await page.getByRole('button', { name: '班级管理', exact: true }).click()
  await expect(page).toHaveURL(/section=classes/)
  await expect(page.getByRole('cell', { name: '物理2401', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '创建班级', exact: true }).click()
  const create = page.getByRole('dialog', { name: '创建班级' })
  await create.getByLabel('班级代码', { exact: true }).fill('PHY2402')
  await create.getByLabel('班级名称', { exact: true }).fill('物理2402')
  await create.getByLabel('负责教师', { exact: true }).click()
  await page.getByText('测试教师 · t0001', { exact: true }).click()
  await create.getByRole('button', { name: /确\s*认\s*创\s*建/ }).click()
  await expect(page.getByRole('status')).toContainText('班级已创建')
  expect(state.writes[0].body).toEqual({ classCode: 'PHY2402', className: '物理2402', semester: '2026秋', teacherId: 'teacher-1' })
  await page.getByRole('searchbox', { name: '搜索班级' }).fill('PHY2402')
  await expect(page.getByRole('cell', { name: '物理2402', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '物理2401', exact: true })).toHaveCount(0)
  await page.getByRole('searchbox', { name: '搜索班级' }).fill('')
  await page.getByRole('button', { name: '查看学生 PHY2401' }).click()
  await expect(page.getByText('名单学生甲', { exact: true })).toBeVisible()
  await expect(page.getByText('待完成', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '关闭', exact: true }).click()

  await page.getByRole('button', { name: '名单导入', exact: true }).click()
  await page.locator('input[type=file]').setInputFiles({ name: 'roster.csv', mimeType: 'text/csv', buffer: Buffer.from('学号,姓名\n20260001,名单学生甲\n20260002,名单学生乙') })
  state.invalidPreview(true)
  await page.getByRole('button', { name: /先预览$/ }).click()
  await expect(page.getByText('第 2 行：学号不能为空')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认导入', exact: true })).toHaveCount(0)
  state.invalidPreview(false)
  await expect(page.getByRole('button', { name: /先预览$/ })).not.toHaveClass(/ant-btn-loading/)
  await page.getByRole('button', { name: /先预览$/ }).click()
  await expect(page.getByText('有效 2 行 · 错误 0 项', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '确认导入', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('导入完成')
  expect(state.writes.at(-1)?.path).toBe('/api/roster-imports/preview-1/commit')

  await page.getByRole('button', { name: '教师目录', exact: true }).click()
  await expect(page.getByRole('cell', { name: 't0001' })).toBeVisible()
  await page.getByRole('button', { name: '班级管理', exact: true }).click()
  await page.getByRole('button', { name: '删除班级 PHY2402' }).click()
  const remove = page.getByRole('dialog', { name: '删除班级', exact: true })
  await remove.getByRole('button', { name: /取\s*消/ }).click()
  expect(state.deletes).toHaveLength(0)
  await page.getByRole('button', { name: '删除班级 PHY2402' }).click()
  await remove.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect.poll(() => state.deletes).toEqual(['/api/classes/class-2'])
  await expect(page.getByRole('cell', { name: '物理2402', exact: true })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('cell', { name: '物理2401', exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('admin-classes.png') })
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.locator('.admin-pro-host')).toHaveCount(0)
  expect((await page.getByLabel('账号', { exact: true }).boundingBox())!.height).toBeGreaterThanOrEqual(48)
  expect(errors).toEqual([])
})

test('server rejections remain visible inside creation and deletion dialogs', async ({ page }) => {
  await mockAdmin(page)
  await page.route('**/api/classes', route => route.request().method() === 'POST'
    ? route.fulfill({ status: 409, json: { error: { code: 'duplicate_class', message: '班级代码已存在' } } }) : route.fallback())
  await page.route('**/api/classes/class-1', route => route.fulfill({ status: 409, json: { error: { code: 'class_has_assignments', message: '该班级已有实验任务，不能删除。' } } }))
  await page.goto('/admin?section=classes')
  await page.getByRole('button', { name: '创建班级', exact: true }).click()
  const create = page.getByRole('dialog', { name: '创建班级', exact: true })
  await create.getByLabel('班级代码', { exact: true }).fill('PHY2401')
  await create.getByLabel('班级名称', { exact: true }).fill('物理2401')
  await create.getByLabel('负责教师', { exact: true }).click()
  await page.getByText('测试教师 · t0001', { exact: true }).click()
  await create.getByRole('button', { name: /确认创建$/ }).click()
  await expect(create.getByRole('alert')).toContainText('班级代码已存在')
  await create.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: '删除班级 PHY2401' }).click()
  const remove = page.getByRole('dialog', { name: '删除班级', exact: true })
  await remove.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(remove.getByRole('alert')).toContainText('该班级已有实验任务，不能删除。')
  await expect(page.getByRole('cell', { name: '物理2401', exact: true })).toHaveCount(1)
})

test('non-admin cannot enter the admin route and student pages do not load Pro components', async ({ page }) => {
  const requests: string[] = []
  page.on('request', request => requests.push(request.url()))
  await mockAdmin(page, 'student')
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/student$/)
  await expect(page.getByRole('heading', { name: '我的实验任务' })).toBeVisible()
  expect(requests.filter(url => /\/assets\/(mount|AdminPage)-/.test(url))).toHaveLength(0)
  expect(requests.some(url => url.includes('/api/teachers'))).toBe(false)
})
