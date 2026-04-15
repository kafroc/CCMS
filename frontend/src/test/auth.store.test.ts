/**
 * Unit tests for the auth Pinia store.
 *
 * All API calls are mocked so tests run offline.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

// Mock the authApi module — tests never hit the network.
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
  },
}))

import { authApi } from '@/api/auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('starts logged-out with no user', () => {
    const store = useAuthStore()
    expect(store.isLoggedIn).toBe(false)
    expect(store.user).toBeNull()
  })

  it('sets token and user after successful login', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      data: {
        access_token: 'tok-abc',
        user: { id: '1', username: 'admin', role: 'admin', must_change_password: false },
      },
    } as any)

    const store = useAuthStore()
    await store.login('admin', 'password')

    expect(store.isLoggedIn).toBe(true)
    expect(store.token).toBe('tok-abc')
    expect(store.user?.username).toBe('admin')
    expect(store.isAdmin).toBe(true)
  })

  it('mustChangePassword reflects user flag', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      data: {
        access_token: 'tok-xyz',
        user: { id: '2', username: 'newbie', role: 'user', must_change_password: true },
      },
    } as any)

    const store = useAuthStore()
    await store.login('newbie', 'TempPw!1')
    expect(store.mustChangePassword).toBe(true)

    store.clearMustChangePassword()
    expect(store.mustChangePassword).toBe(false)
  })

  it('clears state after logout', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      data: {
        access_token: 'tok-abc',
        user: { id: '1', username: 'admin', role: 'admin', must_change_password: false },
      },
    } as any)

    const store = useAuthStore()
    await store.login('admin', 'password')
    store.logout()

    expect(store.isLoggedIn).toBe(false)
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
  })

  it('persists token to localStorage', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      data: {
        access_token: 'tok-persist',
        user: { id: '3', username: 'bob', role: 'user', must_change_password: false },
      },
    } as any)

    const store = useAuthStore()
    await store.login('bob', 'pass')
    expect(localStorage.getItem('token')).toBe('tok-persist')

    store.logout()
    expect(localStorage.getItem('token')).toBeNull()
  })
})
