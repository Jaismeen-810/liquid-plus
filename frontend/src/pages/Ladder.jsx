import { useEffect, useState } from 'react'
import { api, useFetch } from '../api'
import { useFilters } from '../filters'
import LadderChart from '../components/LadderChart'
import BucketTable, { GapMatrix } from '../components/BucketTable'
import Transactions from '../components/Transactions'
import { PageHead, Status } from '../components/ui'

const TEXT = {
  deterministic: ['Deterministic ladder', 'Every deal settles on its contractual maturity date.'],
  ai: ['AI-adjusted ladder', 'Maturities moved earlier by each deal’s predicted chance of early exit or pre-closure.'],
}

export default function Ladder({ view }) {
  const { params, currency, location } = useFilters()
  const [bucket, setBucket] = useState(null)
  const { data, loading, error } = useFetch(`/api/ladder/${view}`, params)
  const rows = data?.totals_by_currency?.[currency] || []
  const [title, note] = TEXT[view]

  useEffect(() => setBucket(null), [params, currency])

  return (
    <>
      <PageHead title={title} note={`${note} ${currency}, ${location || 'all locations'}, as of ${params.run_date}.`}>
        <button onClick={() => api.download('/api/export/ladder', { ...params, currency, view, format: 'xlsx' })}>Export Excel</button>
        <button onClick={() => api.download('/api/export/ladder', { ...params, currency, view, format: 'pdf' })}>Export PDF</button>
      </PageHead>
      <Status loading={loading && !data} error={error} label={view === 'ai' ? 'Running behavioral model' : 'Loading'} />
      {data && !rows.length && <p className="muted">No {currency} positions for this selection.</p>}
      {data && rows.length > 0 && (
        <>
          <div className="split">
            <LadderChart rows={rows} selected={bucket} onSelect={setBucket} currency={currency} />
            <BucketTable rows={rows} selected={bucket} onSelect={setBucket} />
          </div>
          {!location && <GapMatrix series={data.series.filter(s => s.currency === currency)} />}
          {bucket && <Transactions key={bucket} view={view} bucket={bucket} />}
        </>
      )}
    </>
  )
}
