import { useEffect } from 'react'
import { useFetch } from '../api'
import { useFilters } from '../filters'
import { pct } from '../format'
import { Status } from './ui'

export default function Rationale({ id, onClose }) {
  const { params } = useFilters()
  const { data, loading, error } = useFetch(`/api/ml/predictions/${id}`, params)
  const max = Math.max(0.01, ...(data?.drivers || []).map(d => Math.abs(d.contribution)))

  useEffect(() => {
    const close = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])

  return (
    <aside className="drawer" aria-label="Prediction rationale">
      <div className="drawerhead">
        <h2 className="mono">{id}</h2>
        <button className="link" onClick={onClose}>Close</button>
      </div>
      <Status loading={loading} error={error} />
      {data && (
        <>
          <p className="big">{pct(data.p_early)} <span>chance of {data.book === 'asset' ? 'pre-closure' : 'early withdrawal'}</span></p>
          <dl className="facts">
            <dt>Contractual maturity</dt><dd className="num">{data.contractual_maturity}</dd>
            <dt>Adjusted maturity</dt><dd className="num">{data.adjusted_maturity}</dd>
            <dt>Moved earlier by</dt><dd className="num">{data.days_pulled_forward} days</dd>
            <dt>Risk level</dt><dd>{data.risk_level.toLowerCase()}{data.predicted_early ? ', flagged as likely early exit' : ''}</dd>
            <dt>Typical early exit</dt><dd className="num">{data.expected_shift_days} days before maturity</dd>
            <dt>Model</dt><dd>Logistic regression, {data.book} model (threshold {pct(data.threshold)})</dd>
          </dl>
          <p>{data.summary}</p>
          <h3>What drove this prediction</h3>
          <ul className="drivers">
            {data.drivers.map(d => (
              <li key={d.feature}>
                <div><span>{d.feature}</span><span className="muted">{d.value}</span></div>
                <div className="track">
                  <span className={d.contribution > 0 ? 'up' : 'down'} style={{ width: `${(Math.abs(d.contribution) / max) * 100}%` }} />
                </div>
                <small>{d.contribution > 0 ? '+' : '−'}{Math.abs(d.contribution * 100).toFixed(1)} pts, {d.effect}</small>
              </li>
            ))}
          </ul>
          <p className="muted small">Each bar shows how much that factor moves the probability compared with an average transaction. Adjusted maturity = contractual maturity − probability × typical early-exit days.</p>
        </>
      )}
    </aside>
  )
}
