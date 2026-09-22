import { defineStore } from 'pinia'
import { ApiError, authApi, type Role, type UserView, type WorkspaceView } from '../api/client'

type AuthStatus = 'unknown' | 'guest' | 'authenticated'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    status: 'unknown' as AuthStatus,
    user: null as UserView | null,
    workspace: null as WorkspaceView | null,
  }),
  getters: {
    homePath: (state) => (state.user ? `/${state.user.role}` : '/login'),
  },
  actions: {
    async bootstrap() {
      if (this.status !== 'unknown') return
      try {
        this.user = await authApi.me()
        this.status = 'authenticated'
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          this.user = null
          this.status = 'guest'
          return
        }
        throw error
      }
    },
    async login(account: string, password: string) {
      this.user = await authApi.login(account, password)
      this.status = 'authenticated'
      this.workspace = null
    },
    async changePassword(currentPassword: string, newPassword: string) {
      this.user = await authApi.changeInitialPassword(currentPassword, newPassword)
      this.status = 'authenticated'
    },
    async loadWorkspace(role: Role) {
      this.workspace = await authApi.workspace(role)
    },
    async logout() {
      try {
        await authApi.logout()
      } finally {
        this.user = null
        this.workspace = null
        this.status = 'guest'
      }
    },
  },
})
