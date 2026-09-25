import { expect, test } from '@playwright/test'

test('student entry saves locally, syncs after reconnect, and resolves a same-cell conflict', async ({ page }) => {
  const assignmentId = '11111111-1111-4111-8111-111111111111'
  const now = new Date()
  const assignment = {
    id: assignmentId, title: '阶段四录入测试', startAt: new Date(now.getTime() - 3600000).toISOString(),
    dueAt: new Date(now.getTime() + 3600000).toISOString(), status: 'open', editable: true,
    versionId: '22222222-2222-4222-8222-222222222222', versionNumber: 1,
    groupSharingEnabled: false, group: null,
    schema: { title: '阶段四录入测试', tables: [{ id: 'readings', title: '测量记录', minimumRows: 1, maximumRows: 1,
      fields: [
        { key: 'note', label: '备注', symbol: 'x', unit: '1', type: 'text', required: true, scope: 'individual' },
        { key: 'voltage', label: '电压', symbol: 'U₁', unit: 'V', type: 'number', required: false, scope: 'individual' },
      ],
      grid: { rows: 2, columns: 2, cells: [
        { id: 'r1c1', row: 0, column: 0, rowSpan: 1, colSpan: 1, kind: 'label', text: '备注' },
        { id: 'r1c2', row: 0, column: 1, rowSpan: 1, colSpan: 1, kind: 'label', text: '电压' },
        { id: 'r2c1', row: 1, column: 0, rowSpan: 1, colSpan: 1, kind: 'field', text: '', fieldKey: 'note' },
        { id: 'r2c2', row: 1, column: 1, rowSpan: 1, colSpan: 1, kind: 'field', text: '', fieldKey: 'voltage' },
      ] } }], steps: [], calculations: [], charts: [], checks: [], requiredArtifacts: [] },
  }
  let version = 0
  let values: Record<string, string> = {}
  let disconnected = false
  await page.route('**/api/auth/mode', (route) => route.fulfill({ json: { demoEnabled: false, demoAccounts: {} } }))
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: {
    id: '33333333-3333-4333-8333-333333333333', account: '20260001', name: '测试学生', role: 'student',
    mustChangePassword: false, enrollmentCompleted: true, phoneMasked: null,
  } }))
  await page.route('**/api/student/assignments**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/draft')) {
      if (route.request().method() === 'GET') return route.fulfill({ json: { version, values, updatedAt: null, locked: false } })
      if (disconnected) return route.abort('internetdisconnected')
      const payload = route.request().postDataJSON()
      if (payload.baseVersion !== version) return route.fulfill({ status: 409, json: {
        error: { code: 'draft_conflict', message: '草稿已更新', details: { version, values, updatedAt: null, locked: false } },
      } })
      version += 1
      values = payload.values
      return route.fulfill({ json: { version, values, updatedAt: new Date().toISOString(), locked: false } })
    }
    if (path.endsWith(assignmentId)) return route.fulfill({ json: assignment })
    return route.fulfill({ json: [assignment] })
  })

  await page.goto('/student')
  await page.getByRole('button', { name: '录入数据' }).click()
  await expect(page.getByRole('heading', { name: '测量记录' })).toBeVisible()
  const input = page.locator('#readings-r2c1')
  await input.fill('首次读数')
  await expect(page.getByText('已同步', { exact: true })).toBeVisible()
  expect(values['readings:r2c1']).toBe('首次读数')

  disconnected = true
  await input.fill('断网记录')
  await expect(page.getByText('本地已保存', { exact: true })).toBeVisible()
  await page.reload()
  await expect(input).toHaveValue('断网记录')
  disconnected = false
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByText('已同步', { exact: true })).toBeVisible()
  expect(values['readings:r2c1']).toBe('断网记录')

  version += 1
  values = { 'readings:r2c1': '另一设备的值' }
  await input.fill('我当前的值')
  await expect(page.getByText('存在冲突', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保留我的' }).click()
  await expect(page.getByText('已同步', { exact: true })).toBeVisible()
  expect(values['readings:r2c1']).toBe('我当前的值')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await page.locator('#readings-r2c2').focus()
  await page.getByRole('button', { name: '1', exact: true }).click()
  await page.getByRole('button', { name: '.', exact: true }).click()
  await page.getByRole('button', { name: '5', exact: true }).click()
  await expect(page.locator('#readings-r2c2')).toHaveValue('1.5')
  await expect(page.getByText('已同步', { exact: true })).toBeVisible()
  expect(values['readings:r2c2']).toBe('1.5')
})
