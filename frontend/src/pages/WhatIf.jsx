import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useFilters } from '../filters'
import { COLORS, money } from '../format'
import { Money, PageHead } from '../components/ui'

const EMPTY = { value: 0, unit: 'months', direction: 'earlier' }

function ShiftRow({ label, shift, onChange }) {
  const set = key => e => onChange({ ...shift, [key]: key === 'value' ? Number(e.target.value) : e.target.value })
  return (
    <fieldset className="shift">
      <legend>{label}</legend>
      <input type="number" min="0" max="600" value={shift.value} onChange={set('value')} aria-label={`${label} amount`} />
      <select value={shift.unit} onChange={set('unit')} aria-label={`${label} unit`}>
        <option value="days">days</option><option value="weeks">weeks</option><option value="months">months</option>
      </select>
      <select value={shift.direction} onChange={set('direction')} aria-label={`${label} direction`}>
        <option value="earlier">earlier</option><option value="later">later</option>
      </select>
    </fieldset>
  )
}

export default function WhatIf() {
  const { params, currency, location } = useFilters()
  const [assets, setAssets] = useState(EMPTY)
  const [liabilities, setLiabilities] = useState({ ...EMPTY, value: 1 })
  const [result, setResult] = useState(null)
  const [state, setState] = useState({ running: false, error: null })

  async function run(e) {
    e.preventDefault()
    setState({ running: true, error: null })
    try {
      setResult(await api.post('/api/scenario/run', {
        run_date: params.run_date,
        location: params.location,
        currency,
        asset_shift: assets.value ? assets : null,
        liability_shift: liabilities.value ? liabilities : null,
      }))
      setState({ running: false, error: null })
    } catch (error) {
      setState({ running: false, error })
    }
  }

  const base = result?.baseline.totals_by_currency[currency] || []
  const next = result?.scenario.totals_by_currency[currency] || []
  const rows = base.map((b, i) => ({ bucket: b.bucket, baseline: b.net_gap, scenario: next[i]?.net_gap ?? 0 }))

  return (
    <>
      <PageHead title="What-if scenario" note={`Move contractual maturities and see the effect on the ${currency} net gap, ${location || 'all locations'}. The behavioral model is not used here.`} />
      <form className="scenario" onSubmit={run}>
        <ShiftRow label="Asset maturities" shift={assets} onChange={setAssets} />
        <ShiftRow label="Liability maturities" shift={liabilities} onChange={setLiabilities} />
        <button className="primary" disabled={state.running || (!assets.value && !liabilities.value)}>
          {state.running ? 'Recalculating…' : 'Run scenario'}
        </button>
      </form>
      {state.error && <p className="error">{state.error.message}</p>}

      {result && (
        <section>
          <h2>{result.description}</h2>
          <div className="split">
            <div className="chart">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#E6E9EE" />
                  <XAxis dataKey="bucket" tickLine={false} axisLine={{ stroke: '#C9CFD8' }} />
                  <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={64} />
                  <Tooltip formatter={(v, n) => [`${currency} ${money(v)}`, n]} cursor={{ fill: '#F2F4F7' }} />
                  <Legend iconType="square" iconSize={10} />
                  <ReferenceLine y={0} stroke="#8A94A3" />
                  <Bar dataKey="baseline" name="Current net gap" fill={COLORS.deterministic} maxBarSize={40} />
                  <Bar dataKey="scenario" name="Scenario net gap" fill={COLORS.gap} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="grid">
              <thead><tr><th>Bucket</th><th className="r">Current</th><th className="r">Scenario</th><th className="r">Change</th></tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.bucket}>
                    <td>{r.bucket}</td>
                    <td className="r"><Money value={r.baseline} /></td>
                    <td className="r"><Money value={r.scenario} /></td>
                    <td className="r"><Money value={r.scenario - r.baseline} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
