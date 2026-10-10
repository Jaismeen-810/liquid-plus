import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth'
import App from '../App'
import { fx, json, mockApi } from './mockApi'

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true }

const renderApp = () => render(<MemoryRouter initialEntries={['/ladder']} future={FUTURE}><AuthProvider><App /></AuthProvider></MemoryRouter>)

test('shows the backend error for a wrong password', async () => {
  mockApi({ '/api/auth/login': () => json({ error: { message: 'Invalid username or password' } }, 401) })
  renderApp()
  await userEvent.type(screen.getByLabelText('Username'), 'sg_user')
  await userEvent.type(screen.getByLabelText('Password'), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password')
})

test('signs in and opens the deterministic ladder', async () => {
  const fetch = mockApi({ '/api/auth/login': () => json({ access_token: 't', token_type: 'bearer', expires_in: 3600, user: fx.me }) })
  renderApp()
  await userEvent.type(screen.getByLabelText('Username'), 'support_user')
  await userEvent.type(screen.getByLabelText('Password'), 'secret-pass')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('heading', { name: 'Deterministic ladder' })).toBeInTheDocument()
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ username: 'support_user', password: 'secret-pass' })
  expect(sessionStorage.getItem('token')).toBe('t')
})
