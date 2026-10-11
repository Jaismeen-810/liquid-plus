import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth'
import App from '../App'
import { today } from '../filters'
import { fx, mockApi } from './mockApi'

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true }

function open(path, user = fx.me) {
  sessionStorage.setItem('token', 'test-token')
  const fetch = mockApi({ '/api/auth/me': () => Promise.resolve(new Response(JSON.stringify(user), { headers: { 'Content-Type': 'application/json' } })) })
  render(<MemoryRouter initialEntries={[path]} future={FUTURE}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  return fetch
}

test('deterministic ladder shows buckets and drills into transactions', async () => {
  open('/ladder')
  const row = await screen.findByRole('row', { name: /^1-3M/ })
  await userEvent.click(row)
  expect(await screen.findByText(fx.txDet.items[0].transaction_id)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: /Net gap by location/ })).toBeInTheDocument()
})

test('AI ladder opens the prediction rationale panel', async () => {
  open('/ai')
  await userEvent.click(await screen.findByRole('row', { name: /^1-5Y/ }))
  await userEvent.click(await screen.findByText(fx.txAi.items[0].transaction_id))
  const panel = await screen.findByRole('complementary', { name: 'Prediction rationale' })
  expect(await within(panel).findByText('What drove this prediction')).toBeInTheDocument()
  expect(within(panel).getByText(fx.rationale.drivers[0].feature)).toBeInTheDocument()
})

test('comparison lists actions for a clicked bucket', async () => {
  open('/compare')
  await userEvent.click(await screen.findByRole('row', { name: /^0-1M/ }))
  expect(await screen.findByText(fx.recs[0].action_text)).toBeInTheDocument()
})

test('what-if runs a scenario', async () => {
  open('/what-if')
  await userEvent.click(await screen.findByRole('button', { name: 'Run scenario' }))
  expect(await screen.findByRole('heading', { name: fx.scenario.description })).toBeInTheDocument()
})

test('recommendations and analytics render', async () => {
  open('/actions')
  expect(await screen.findByText(fx.recs[0].action_text)).toBeInTheDocument()
  cleanupAndOpen('/history')
  expect(await screen.findByRole('heading', { name: 'Deposit outflow anomalies' })).toBeInTheDocument()
})

test('data page is support-only', async () => {
  open('/data')
  expect(await screen.findByRole('heading', { name: 'Behavioral models' })).toBeInTheDocument()
  expect(await screen.findByText('Liability model')).toBeInTheDocument()
})

test('branch user cannot pick another location or open the data page', async () => {
  open('/data', { ...fx.me, role: 'BRANCH', location: 'Singapore', username: 'sg_user' })
  expect(await screen.findByRole('heading', { name: 'Deterministic ladder' })).toBeInTheDocument()
  expect(screen.getByLabelText('Location')).toBeDisabled()
  expect(screen.queryByRole('link', { name: 'Data and models' })).not.toBeInTheDocument()
})

function cleanupAndOpen(path) {
  document.body.innerHTML = ''
  open(path)
}

test('as-of calendar defaults to today and drives the API date', async () => {
  const fetch = open('/ladder')
  const input = await screen.findByLabelText('As of date')
  expect(input).toHaveValue(today())
  fireEvent.change(input, { target: { value: '2026-12-31' } })
  await screen.findByRole('row', { name: /^1-3M/ })
  const urls = fetch.mock.calls.map(c => String(c[0]))
  expect(urls.some(u => u.includes('/api/ladder/deterministic?') && u.includes('run_date=2026-12-31'))).toBe(true)
})
