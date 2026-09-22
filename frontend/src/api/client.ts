export type Role = 'student' | 'teacher' | 'admin'

export interface UserView {
  id: string
  account: string
  name: string
  role: Role
  mustChangePassword: boolean
}

export interface WorkspaceView {
  role: Role
  title: string
  description: string
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData
  const response = await fetch(path, {
    credentials: 'include',
    headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...init.headers },
    ...init,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(
      body?.error?.code || 'request_failed',
      body?.error?.message || '请求失败，请稍后再试。',
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const authApi = {
  login: (account: string, password: string) =>
    request<UserView>('/api/auth/login', { method: 'POST', body: JSON.stringify({ account, password }) }),
  me: () => request<UserView>('/api/auth/me'),
  changeInitialPassword: (currentPassword: string, newPassword: string) =>
    request<UserView>('/api/auth/change-initial-password', {
      method: 'POST',
      body: JSON.stringify({ currentPassword, newPassword }),
    }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  workspace: (role: Role) => request<WorkspaceView>(`/api/workspaces/${role}`),
}

export interface ClassView {
  id: string
  classCode: string
  className: string
  semester: string
  teacherId: string
  teacherName: string
  studentCount: number
}
export interface TeacherView { id: string; account: string; name: string }
export interface StudentView { id: string; account: string; name: string; studentNumber: string; joinedAt: string }

export interface ImportIssue { row: number; field: string; message: string }
export interface ImportPreview {
  id: string
  classId: string
  sourceName: string
  status: string
  validCount: number
  errorCount: number
  errors: ImportIssue[]
}
export interface ImportResult {
  id: string
  created: number
  existing: number
  membershipsAdded: number
  initialCredentials: { account: string; initialPassword: string }[]
}

export interface TemplateView {
  id: string
  name: string
  description: string
  status: string
  schema: Record<string, unknown>
  versionCount: number
  latestVersionId: string | null
}

export interface ValidationView {
  valid: boolean
  issues: { path: string; message: string }[]
}

export interface AssignmentView {
  id: string
  templateVersionId: string
  classId: string
  title: string
  startAt: string
  dueAt: string
  status: string
  templateName: string
  versionNumber: number
  className: string
  classCode: string
}

export const managementApi = {
  listTeachers: () => request<TeacherView[]>('/api/teachers'),
  listClasses: () => request<ClassView[]>('/api/classes'),
  createClass: (payload: { classCode: string; className: string; semester: string; teacherId?: string }) =>
    request<ClassView>('/api/classes', { method: 'POST', body: JSON.stringify(payload) }),
  listClassStudents: (classId: string) => request<StudentView[]>(`/api/classes/${classId}/students`),
  deleteClass: (classId: string) => request<void>(`/api/classes/${classId}`, { method: 'DELETE' }),
  previewRoster: (classId: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<ImportPreview>(`/api/roster-imports/preview?class_id=${encodeURIComponent(classId)}`, { method: 'POST', body })
  },
  commitRoster: (id: string) => request<ImportResult>(`/api/roster-imports/${id}/commit`, { method: 'POST' }),
  listTemplates: () => request<TemplateView[]>('/api/templates'),
  createTemplate: (name: string, description: string) =>
    request<TemplateView>('/api/templates', { method: 'POST', body: JSON.stringify({ name, description }) }),
  saveTemplate: (id: string, name: string, description: string, schema: Record<string, unknown>) =>
    request<TemplateView>(`/api/templates/${id}/draft`, {
      method: 'PUT', body: JSON.stringify({ name, description, schema }),
    }),
  validateTemplate: (id: string) => request<ValidationView>(`/api/templates/${id}/validate`, { method: 'POST' }),
  publishTemplate: (id: string) => request<{ id: string; versionNumber: number }>(`/api/templates/${id}/publish`, { method: 'POST' }),
  listAssignments: () => request<AssignmentView[]>('/api/assignments'),
  createAssignment: (payload: { templateVersionId: string; classId: string; title: string; startAt: string; dueAt: string }) =>
    request<{ id: string; status: string }>('/api/assignments', { method: 'POST', body: JSON.stringify(payload) }),
}
