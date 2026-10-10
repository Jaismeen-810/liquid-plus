import { useState } from 'react'
import { api } from '../api'
import { useFilters } from '../filters'
import { CURRENCIES } from '../format'
import { PageHead } from '../components/ui'
import RecommendationList from '../components/RecommendationList'

export default function Recommendations() {
  const { params, location } = useFilters()
  const [currency, setCurrency] = useState('')
  const [severity, setSeverity] = useState('')

  return (
    <>
      <PageHead title="Recommendations" note={`Actions for buckets where the AI-adjusted gap is material, ${location || 'all locations'}. Most urgent first.`}>
        <select value={currency} onChange={e => setCurrency(e.target.value)} aria-label="Currency">
          <option value="">All currencies</option>
          {CURRENCIES.map(c => <option key={c}>{c}</option>)}
        </select>
        <select value={severity} onChange={e => setSeverity(e.target.value)} aria-label="Severity">
          <option value="">All severities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
        </select>
        <button onClick={() => api.download('/api/export/recommendations', { ...params, currency: currency || undefined, format: 'xlsx' })}>Export Excel</button>
        <button onClick={() => api.download('/api/export/recommendations', { ...params, currency: currency || undefined, format: 'pdf' })}>Export PDF</button>
      </PageHead>
      <RecommendationList filters={{ ...params, currency: currency || undefined }} severity={severity} />
    </>
  )
}
