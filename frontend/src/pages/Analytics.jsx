import { useMemo, useState } from 'react'
import { CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts'
import { useFetch } from '../api'
import { useFilters } from '../filters'
import { COLORS, money } from '../format'
import { PageHead, Status } from '../components/ui'

const SERIES_COLORS = ['#1F3A5F', '#3D8B6E', '#B5533C', '#8A6D2F', '#6B5B95', '#4E8FA8', '#A3ADBA', '#7A4E3B', '#5E7D3A', '#9C4F7A']
const GROUPS = { product_type: 'Product type', customer_segment: 'Customer segment', type: 'Asset vs liability' }

export default function Analytics() {
  const { params, currency, location } = useFilters()
  const [groupBy, setGroupBy] = useState('customer_segment')
  const [days, setDays] = useState(365)
  const scope = { location: params.location, currency }
  const trends = useFetch('/api/analytics/exit-trends', { ...scope, group_by: groupBy })
  const anomalies = useFetch('/api/analytics/anomalies', { ...scope, days })

  const { rows, groups } = useMemo(() => {
    const byPeriod = {}
    const names = new Set()
    for (const p of trends.data?.points || []) {
      names.add(p.group)
      byPeriod[p.period] = { ...byPeriod[p.period], period: p.period, [p.group]: Math.round(p.early_exit_rate * 1000) / 10 }
    }
    return { rows: Object.values(byPeriod).sort((a, b) => a.period.localeCompare(b.period)), groups: [...names].sort() }
  }, [trends.data])

  const points = anomalies.data?.points || []
  const flagged = points.filter(p => p.is_anomaly)

  return (
    <>
      <PageHead title="Behavioral analytics" note={`Historical behavior for ${currency}, ${location || 'all locations'}.`} />

      <section>
        <div className="sectionhead">
          <h2>Early exit rate by month of closure</h2>
          <select value={groupBy} onChange={e => setGroupBy(e.target.value)} aria-label="Group by">
            {Object.entries(GROUPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <Status loading={trends.loading} error={trends.error} />
        {rows.length > 0 && (
          <div className="chart">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#E6E9EE" />
                <XAxis dataKey="period" tickLine={false} minTickGap={24} axisLine={{ stroke: '#C9CFD8' }} />
                <YAxis unit="%" tickLine={false} axisLine={false} width={48} />
                <Tooltip formatter={v => `${v}%`} />
                <Legend iconType="plainline" />
                {groups.map((g, i) => <Line key={g} dataKey={g} stroke={SERIES_COLORS[i % SERIES_COLORS.length]} dot={false} strokeWidth={1.75} connectNulls />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section>
        <div className="sectionhead">
          <h2>Deposit outflow anomalies</h2>
          <select value={days} onChange={e => setDays(Number(e.target.value))} aria-label="Period">
            <option value={90}>Last 90 days</option><option value={180}>Last 180 days</option><option value={365}>Last 365 days</option>
          </select>
        </div>
        <Status loading={anomalies.loading} error={anomalies.error} />
        {anomalies.data && (
          <>
            <p className="muted">
              Days where deposit outflow was at least {anomalies.data.multiplier}× the previous {anomalies.data.window_days}-day average.
              {' '}{flagged.length} flagged.
            </p>
            <div className="chart">
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#E6E9EE" />
                  <XAxis dataKey="date" tickLine={false} minTickGap={40} axisLine={{ stroke: '#C9CFD8' }} />
                  <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={64} />
                  <Tooltip formatter={(v, n) => [money(v), n]} />
                  <Legend iconType="plainline" />
                  <Line dataKey="outflow" name="Daily outflow" stroke="#A3ADBA" dot={false} strokeWidth={1} />
                  <Line dataKey="rolling_avg" name="Rolling average" stroke={COLORS.gap} dot={false} strokeWidth={2} />
                  <Scatter data={flagged} dataKey="outflow" name="Anomaly" fill={COLORS.flag} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            {flagged.length > 0 && (
              <table className="grid">
                <thead><tr><th>Date</th><th className="r">Outflow</th><th className="r">Average</th><th>Alert</th></tr></thead>
                <tbody>
                  {[...flagged].reverse().map(p => (
                    <tr key={p.date}>
                      <td className="num">{p.date}</td>
                      <td className="r num">{money(p.outflow)}</td>
                      <td className="r num">{money(p.rolling_avg)}</td>
                      <td className="neg">{p.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </section>
    </>
  )
}
