import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../src/stores/auth'

const student = {
  id: '74c96c20-b0f4-4a4c-8c6e-402244f118ea',
  account: '20260001',
  name: '测试学生',
  role: 'student',
  mustChangePassword: false,
}

describe('auth store through the HTTP interface', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('keeps the server identity after login', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(student), { status: 200 })))
    const auth = useAuthStore()

    await auth.login('20260001', 'InitialPass2026')

    expect(auth.user).toEqual(student)
    expect(auth.homePath).toBe('/student')
    expect(auth.user?.mustChangePassword).toBe(false)
  })

  it('treats a 401 bootstrap response as a guest session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'unauthenticated', message: '请先登录。' } }), { status: 401 }),
      ),
    )
    const auth = useAuthStore()

    await auth.bootstrap()

    expect(auth.status).toBe('guest')
    expect(auth.user).toBeNull()
  })
})
