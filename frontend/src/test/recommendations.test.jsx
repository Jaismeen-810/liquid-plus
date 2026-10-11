import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth'
import App from '../App'
import { fx, mockApi } from './mockApi'

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true }

function openRecommendations() {
  sessionStorage.setItem('token', 'test-token')
  mockApi()
  return render(
    <MemoryRouter initialEntries={['/actions']} future={FUTURE}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>
  )
}

test('recommendations dashboard displays actionable cards, KPI metrics, and reason on main screen', async () => {
  openRecommendations()

  // 1. Heading and KPI Metrics banner
  expect(await screen.findByRole('heading', { name: 'Treasury Recommendations' })).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Funding required' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Potential investment' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Risk alerts' })).toBeInTheDocument()

  // 2. Actionable card rendering with exact action text
  expect(await screen.findByText(fx.recs[0].action_text)).toBeInTheDocument()

  // 3. Reason banner
  const reasons = await screen.findAllByText(/Reason:/)
  expect(reasons.length).toBeGreaterThan(0)

  // 4. No drill-down drawer or buttons on screen
  expect(screen.queryByRole('button', { name: 'View affected transactions' })).not.toBeInTheDocument()
  expect(screen.queryByRole('complementary', { name: 'Recommendation details' })).not.toBeInTheDocument()
})

test('rule filter tabs filter recommendations', async () => {
  openRecommendations()

  const ruleATab = await screen.findByRole('button', { name: /Rule A: Raise funding/ })
  await userEvent.click(ruleATab)
  expect(ruleATab).toHaveClass('active')

  const ruleBTab = screen.getByRole('button', { name: /Rule B: Deploy surplus/ })
  await userEvent.click(ruleBTab)
  expect(ruleBTab).toHaveClass('active')

  const allRulesTab = screen.getByRole('button', { name: 'All rules' })
  await userEvent.click(allRulesTab)
  expect(allRulesTab).toHaveClass('active')
})
