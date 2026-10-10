import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useFetch } from '../api'
import { useFilters } from '../filters'
import { COLORS, money } from '../format'
import { Money, PageHead, Status } from '../components/ui'
import RecommendationList from '../components/RecommendationList'

export default function Compare() {
  const { params, currency, location } = useFilters()
  const [bucket, setBucket] = useState(null)
  const { data, loading, error } = useFetch('/api/ladder/compare', params)
  const rows = data?.currencies.find(c => c.currency === currency)?.buckets || []

  return (
    <>
      <PageHead title="Deterministic vs AI-adjusted" note={`Net gap per bucket, ${currency}, ${location || 'all locations'}. The difference is the liquidity impact of customer behavior.`} />
      <Status loading={loading} error={error} label="Running behavioral model" />
      {data && !rows.length && <p className="muted">No {currency} positions for this selection.</p>}
      {rows.length > 0 && (
        <>
          <div className="split">
            <div className="chart">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={rows} onClick={s => s?.activeLabel && setBucket(s.activeLabel)} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#E6E9EE" />
                  <XAxis dataKey="bucket" tickLine={false} axisLine={{ stroke: '#C9CFD8' }} />
                  <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={64} />
                  <Tooltip formatter={(v, n) => [`${currency} ${money(v)}`, n]} cursor={{ fill: '#F2F4F7' }} />
                  <Legend iconType="square" iconSize={10} />
                  <ReferenceLine y={0} stroke="#8A94A3" />
                  <Bar dataKey="deterministic_gap" name="Deterministic" fill={COLORS.deterministic} maxBarSize={40} cursor="pointer" />
                  <Bar dataKey="ai_gap" name="AI-adjusted" fill={COLORS.ai} maxBarSize={40} cursor="pointer" />
                </BarChart>
              </ResponsiveContainer>
              <p className="hint">Click a bucket to see its recommended actions.</p>
            </div>
            <table className="grid clickable">
              <thead><tr><th>Bucket</th><th className="r">Deterministic</th><th className="r">AI-adjusted</th><th className="r">Change</th><th className="r">Actions</th></tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.bucket} className={bucket === r.bucket ? 'on' : ''} onClick={() => setBucket(r.bucket)}>
                    <td>{r.bucket}</td>
                    <td className="r"><Money value={r.deterministic_gap} /></td>
                    <td className="r"><Money value={r.ai_gap} /></td>
                    <td className="r"><Money value={r.difference} /></td>
                    <td className="r num">{r.recommendation_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {bucket && (
            <section>
              <h2>Recommended actions for {bucket}</h2>
              <RecommendationList filters={{ ...params, currency, bucket }} />
            </section>
          )}
        </>
      )}
    </>
  )
}
