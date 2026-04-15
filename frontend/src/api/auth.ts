import request from './request'

export interface LoginResult {
  access_token: string
  token_type: string
  user: {
    id: string
    username: string
    role: string
  }
}

export const authApi = {
  login(username: string, password: string) {
    // FastAPI OAuth2PasswordRequestForm requires form-data format
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    return request.post<any, { code: number; data: LoginResult }>('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },

  getMe() {
    return request.get<any, { code: number; data: { id: string; username: string; role: string } }>('/auth/me')
  },
}
