import { expect, test, type Page } from '@playwright/test'

const assignmentId = '11111111-1111-4111-8111-111111111111'

async function mockStudent(page: Page) {
  let version = 0
  let values: Record<string, string> = {}
  let sharedValues: Record<string, string> = {}
  let sharedVersion = 0
  let connected = true
  const assignment = {
    id: assignmentId, title: '大学物理实验：电压测量与横竖屏数据记录验证',
    startAt: '2026-01-01T00:00:00Z', dueAt: '2027-01-01T00:00:00Z',
    status: 'open', editable: true, versionId: 'version-1', versionNumber: 1,
    groupSharingEnabled: true, group: { id: 'group-1', name: '第一实验小组' },
    schema: {
      title: '电压测量', description: '按教师模板记录，不要遗漏任何测量项。',
      steps: [{ id: 'measure', title: '测量与记录', instruction: '先调零，再依次填写各测量项，横向滑动查看全部数据。', tableId: 'readings' }],
      tables: [{
        id: 'readings', title: '测量记录', description: '保留合并表头及所有字段。', minimumRows: 1, maximumRows: 1,
        fields: [
          { key: 'voltage', label: '电压', symbol: 'U₁', unit: 'V', type: 'number', required: true, scope: 'individual' },
          { key: 'note', label: '备注', symbol: '', unit: '', type: 'text', required: false, scope: 'individual' },
          { key: 'direction', label: '方向', symbol: '', unit: '', type: 'enum', options: ['正向', '反向'], required: false, scope: 'individual' },
          { key: 'shared', label: '共享读数', symbol: 'I', unit: 'mA', type: 'number', required: false, scope: 'group' },
        ],
        grid: { rows: 2, columns: 4, cells: [
          { id: 'header', row: 0, column: 0, rowSpan: 1, colSpan: 4, kind: 'label', text: '测量数据：电压、备注、方向及组内共享读数' },
          ...['voltage', 'note', 'direction', 'shared'].map((fieldKey, column) => ({
            id: `value${column}`, row: 1, column, rowSpan: 1, colSpan: 1, kind: 'field', text: '', fieldKey,
          })),
        ] },
      }], calculations: [], charts: [], checks: [], requiredArtifacts: [],
    },
  }
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/auth/mode') return route.fulfill({ json: { demoEnabled: false, demoAccounts: {} } })
    if (path === '/api/auth/me') return route.fulfill({ json: {
      id: 'responsive-student', name: '测试学生', account: '20260001', role: 'student', enrollmentCompleted: true,
    } })
    if (path.endsWith('/draft') || path.endsWith('/shared')) {
      const isShared = path.endsWith('/shared')
      const snapshot = () => ({ version: isShared ? sharedVersion : version, values: isShared ? sharedValues : values, sources: {}, locked: !assignment.editable, updatedAt: null })
      if (request.method() === 'GET') return route.fulfill({ json: snapshot() })
      if (!connected) return route.abort('internetdisconnected')
      const payload = request.postDataJSON()
      if (payload.baseVersion !== snapshot().version) return route.fulfill({ status: 409, json: {
        error: { code: 'draft_conflict', message: '草稿已更新', details: snapshot() },
      } })
      if (isShared) { sharedVersion++; sharedValues = payload.values }
      else { version++; values = payload.values }
      return route.fulfill({ json: snapshot() })
    }
    if (path === `/api/student/assignments/${assignmentId}`) return route.fulfill({ json: assignment })
    if (path === '/api/student/assignments') return route.fulfill({ json: [assignment] })
    return route.fulfill({ status: 404, json: {} })
  })
  return {
    assignment, getValues: () => values, getShared: () => sharedValues,
    disconnect: () => { connected = false }, reconnect: () => { connected = true },
    externalEdit: () => { version++; values = { ...values, 'readings:value1': '另一设备修改' } },
  }
}

async function expectPageFits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
}

test('student phone/tablet layout preserves entry, shared saves, offline recovery, conflicts and read-only rules', async ({ page }, info) => {
  const state = await mockStudent(page)
  const touch = info.project.use.hasTouch === true
  await page.goto('/student')
  await expect(page.getByRole('heading', { name: '我的实验任务' })).toBeVisible()
  await expectPageFits(page)
  await page.getByRole('button', { name: '录入数据' }).click()
  await expect(page.getByRole('heading', { name: '测量记录' })).toBeVisible()
  await expectPageFits(page)
  await expect(page.locator('.entry-table th')).toHaveAttribute('colspan', '4')
  const region = page.getByRole('region', { name: '测量记录，可横向滚动' })
  if (page.viewportSize()!.width < 1000) {
    expect(await region.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
  }
  const numeric = page.locator('#readings-value0')
  if (touch) {
    await numeric.click()
    const keypad = page.getByRole('complementary', { name: '实验数据数字键盘' })
    await expect(keypad).toBeVisible()
    const rect = (await keypad.boundingBox())!
    expect(rect.x).toBeGreaterThanOrEqual(0)
    expect(rect.x + rect.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
    const inputRect = (await numeric.boundingBox())!
    expect(inputRect.y).toBeGreaterThanOrEqual(0)
    expect(inputRect.y + inputRect.height).toBeLessThanOrEqual(rect.y)
    for (const token of ['负号', '1', '.', '5']) await keypad.getByRole('button', { name: token, exact: true }).click()
    await expect(numeric).toHaveValue('-1.5')
    await page.screenshot({ path: info.outputPath('student-keypad.png') })
    const portrait = page.viewportSize()!
    await page.setViewportSize({ width: portrait.height, height: portrait.width })
    await expect(numeric).toHaveValue('-1.5')
    await expect.poll(async () => {
      const input = (await numeric.boundingBox())!
      const keyboard = (await keypad.boundingBox())!
      return input.y >= 0 && input.y + input.height <= keyboard.y
    }).toBe(true)
    await page.setViewportSize(portrait)
    await keypad.getByRole('button', { name: '完成', exact: true }).click()
  } else await numeric.fill('-1.5')
  await expect.poll(() => state.getValues()['readings:value0']).toBe('-1.5')

  const note = page.locator('#readings-value1')
  await note.fill('横竖屏记录')
  await expect.poll(() => state.getValues()['readings:value1']).toBe('横竖屏记录')
  await page.locator('#readings-value2').selectOption('反向')
  await expect.poll(() => state.getValues()['readings:value2']).toBe('反向')
  const shared = page.locator('#readings-value3')
  if (touch) {
    await shared.click()
    await page.getByRole('complementary', { name: '实验数据数字键盘' }).getByRole('button', { name: '3', exact: true }).click()
    await page.getByRole('button', { name: '完成', exact: true }).click()
  } else await shared.fill('3')
  await expect.poll(() => state.getShared()['readings:value3']).toBe('3')

  state.disconnect()
  await note.fill('断网记录')
  await expect(page.getByText('本地已保存', { exact: true })).toBeVisible()
  await page.reload()
  await expect(note).toHaveValue('断网记录')
  state.reconnect()
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect.poll(() => state.getValues()['readings:value1']).toBe('断网记录')
  state.externalEdit()
  await note.fill('保留本机记录')
  await expect(page.getByText('存在冲突', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保留我的', exact: true }).click()
  await expect.poll(() => state.getValues()['readings:value1']).toBe('保留本机记录')
  const original = page.viewportSize()!
  await page.setViewportSize({ width: original.height, height: original.width })
  await expect(note).toHaveValue('保留本机记录')
  await expect(numeric).toHaveValue('-1.5')
  await expectPageFits(page)
  await page.setViewportSize(original)
  await page.screenshot({ path: info.outputPath('student-entry.png') })
  state.assignment.editable = false
  await page.reload()
  await expect(numeric).toBeDisabled()
  await expect(shared).toBeDisabled()
  await expect(page.getByText('当前不在开放时间内，数据不可修改。')).toBeVisible()
})

test('shared sign-in and enrollment fit student screens', async ({ page }, info) => {
  await page.route('**/api/auth/mode', route => route.fulfill({ json: { demoEnabled: false, demoAccounts: {} } }))
  await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { error: { code: 'unauthenticated', message: '请登录' } } }))
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '登录 LabMate' })).toBeVisible()
  await expectPageFits(page)
  await page.getByRole('tab', { name: '学生首次登录' }).click()
  await expect(page.getByRole('heading', { name: '学生首次设置' })).toBeVisible()
  await expect(page.getByRole('button', { name: '获取验证码' })).toBeVisible()
  await expectPageFits(page)
  await page.screenshot({ path: info.outputPath('student-enrollment.png') })
})

test('resizing without reload switches numeric input mode without clearing values', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Checks crossing desktop/phone breakpoints with a fine pointer')
  await mockStudent(page)
  await page.goto(`/student/assignments/${assignmentId}`)
  const numeric = page.locator('#readings-value0')
  await numeric.fill('12')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(numeric).toHaveAttribute('readonly', '')
  await numeric.click()
  await page.getByRole('button', { name: '3', exact: true }).click()
  await expect(numeric).toHaveValue('123')
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(numeric).not.toHaveAttribute('readonly', '')
  await expect(page.getByRole('complementary', { name: '实验数据数字键盘' })).toHaveCount(0)
  await numeric.fill('1234')
  await expect(numeric).toHaveValue('1234')
})
