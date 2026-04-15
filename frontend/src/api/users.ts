import request from './request'

export interface User {
  id: string
  username: string
  role: string
  created_at: string
  toe_permissions: Array<{
    toe_id: string
    toe_name: string
    access_level: string
  }>
}

export const userApi = {
  list() {
    return request.get<any, { code: number; data: User[] }>('/users')
  },

  create(data: { username: string; password: string; role: string }) {
    return request.post<any, { code: number; data: User }>('/users', data)
  },

  updateToePermissions(userId: string, data: Array<{ toe_id: string; access_level: string }>) {
    return request.put<any, { code: number; data: User }>(`/users/${userId}/toe-permissions`, data)
  },

  changePassword(userId: string, data: { old_password: string; new_password: string }) {
    return request.put(`/users/${userId}/password`, data)
  },

  delete(userId: string) {
    return request.delete(`/users/${userId}`)
  },
}
