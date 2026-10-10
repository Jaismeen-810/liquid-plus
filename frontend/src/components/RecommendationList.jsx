import { useFetch } from '../api'
import { Money, Status } from './ui'

export default function RecommendationList({ filters, severity = '' }) {
  const { data, loading, error } = useFetch('/api/recommendations', filters)
  const items = (data || []).filter(r => !severity || r.severity === severity)

  return (
    <>
      <Status loading={loading} error={error} />
      {data && !items.length && <p className="muted">No material gaps here. No action needed.</p>}
      {items.length > 0 && (
        <ol className="recs">
          {items.map(r => (
            <li key={r.id} className={r.severity}>
              <div className="rec-main">
                <span className="sev">{r.severity}</span>
                <strong>{r.action_text}</strong>
              </div>
              <div className="rec-meta">
                <span>{r.location}</span><span>{r.currency}</span><span>{r.bucket}</span>
                <span>AI gap <Money value={r.ai_gap} /></span>
                <span>Deterministic <Money value={r.deterministic_gap} /></span>
              </div>
              {r.rationale && <p className="muted small">{r.rationale}</p>}
            </li>
          ))}
        </ol>
      )}
    </>
  )
}
