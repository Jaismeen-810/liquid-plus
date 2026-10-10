import { api, ApiError, buildUrl, setToken } from '../api'
import { json } from './mockApi'

test('buildUrl drops empty parameters', () => {
  const url = buildUrl('/api/ladder/ai', { run_date: '2026-10-10', location: undefined, currency: '' })
  expect(url.pathname).toBe('/api/ladder/ai')
  expect(url.search).toBe('?run_date=2026-10-10')
})

test('sends the bearer token', async () => {
  setToken('abc')
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(() => json({ ok: true }))
  await api.get('/api/auth/me')
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer abc')
  setToken(null)
})

test('server errors become ApiError with the backend message', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => json({ error: { code: 'forbidden', message: 'No access' } }, 403))
  const err = await api.get('/api/ladder/ai').catch(e => e)
  expect(err).toBeInstanceOf(ApiError)
  expect(err.status).toBe(403)
  expect(err.message).toBe('No access')
})

test('a 401 clears the session', async () => {
  setToken('expired')
  const expired = vi.fn()
  window.addEventListener('session-expired', expired)
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => json({ error: { message: 'Session expired' } }, 401))
  await api.get('/api/auth/me').catch(() => {})
  expect(sessionStorage.getItem('token')).toBeNull()
  expect(expired).toHaveBeenCalled()
})
