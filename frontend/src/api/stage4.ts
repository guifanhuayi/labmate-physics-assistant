import { request } from './client'

export interface StudentAssignmentSummary {
  id: string
  title: string
  startAt: string
  dueAt: string
  status: string
  editable: boolean
  versionNumber: number
  groupSharingEnabled: boolean
}

export interface StudentAssignment extends StudentAssignmentSummary {
  versionId: string
  schema: Record<string, unknown>
  group: { id: string; name: string } | null
}

export interface DataSnapshot {
  version: number
  values: Record<string, string>
  updatedAt: string | null
  locked: boolean
  sources?: Record<string, { editorId: string; editorName: string; editedAt: string }>
  groupId?: string
  groupName?: string
}

export interface ExperimentGroup {
  id: string
  name: string
  memberIds: string[]
  members: { id: string; name: string; studentNumber: string }[]
}

export const stage4Api = {
  studentAssignments: () => request<StudentAssignmentSummary[]>('/api/student/assignments'),
  studentAssignment: (id: string) => request<StudentAssignment>(`/api/student/assignments/${id}`),
  draft: (id: string) => request<DataSnapshot>(`/api/student/assignments/${id}/draft`),
  shared: (id: string) => request<DataSnapshot>(`/api/student/assignments/${id}/shared`),
  saveDraft: (id: string, baseVersion: number, values: Record<string, string>, requestId: string) =>
    request<DataSnapshot>(`/api/student/assignments/${id}/draft`, {
      method: 'PUT', body: JSON.stringify({ baseVersion, values, requestId }),
    }),
  saveShared: (id: string, baseVersion: number, values: Record<string, string>, requestId: string) =>
    request<DataSnapshot>(`/api/student/assignments/${id}/shared`, {
      method: 'PUT', body: JSON.stringify({ baseVersion, values, requestId }),
    }),
  groups: (id: string) => request<ExperimentGroup[]>(`/api/assignments/${id}/groups`),
  createGroup: (id: string, name: string, memberIds: string[]) =>
    request<ExperimentGroup>(`/api/assignments/${id}/groups`, {
      method: 'POST', body: JSON.stringify({ name, memberIds }),
    }),
  setMembers: (id: string, groupId: string, memberIds: string[]) =>
    request<ExperimentGroup>(`/api/assignments/${id}/groups/${groupId}/members`, {
      method: 'PUT', body: JSON.stringify({ memberIds }),
    }),
  setSharing: (id: string, enabled: boolean) =>
    request<{ groupSharingEnabled: boolean }>(`/api/assignments/${id}/sharing`, {
      method: 'PUT', body: JSON.stringify({ enabled }),
    }),
}
