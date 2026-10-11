import { useFetch } from '../api'
import { formatCurrency } from '../format'
import { Money, Status } from './ui'

export default function RecommendationList({
  filters,
  severity = '',
  ruleCode = '',
  viewMode = 'cards',
}) {
  const { data, loading, error } = useFetch('/api/recommendations', filters)

  const items = (data || []).filter(r => {
    if (severity && r.severity !== severity) return false
    if (ruleCode && r.rule_code !== ruleCode) return false
    return true
  })

  return (
    <>
      <Status loading={loading} error={error} />
      {data && !items.length && (
        <p className="muted" style={{ padding: '24px 0' }}>
          No material liquidity gaps or recommended actions for this selection.
        </p>
      )}

      {items.length > 0 && (
        <>
          {viewMode === 'compact' ? (
            <ol className="recs">
              {items.map(r => (
                <li key={r.id} className={r.severity}>
                  <div className="rec-main">
                    <span className="sev">{r.severity}</span>
                    <strong>{r.action_text}</strong>
                  </div>
                  <div className="rec-meta">
                    <span>{r.location}</span>
                    <span>{r.currency}</span>
                    <span>{r.bucket}</span>
                    <span>AI gap <Money value={r.ai_gap} /></span>
                    <span>Deterministic <Money value={r.deterministic_gap} /></span>
                  </div>
                  {r.reason && (
                    <p className="rec-card-reason" style={{ margin: '6px 0 4px 64px' }}>
                      <strong>Reason:</strong> {r.reason}
                    </p>
                  )}
                  {r.rationale && <p className="muted small">{r.rationale}</p>}
                </li>
              ))}
            </ol>
          ) : (
            <div className="rec-cards-grid">
              {items.map(r => {
                const currency = r.currency || 'EUR'
                const isShortfall = r.gap_type === 'shortfall' || r.ai_gap < 0
                const isRiskAlert = r.rule_code === 'RULE_C' || r.gap_type === 'risk_alert'
                const isSurplus = r.rule_code === 'RULE_B' || r.gap_type === 'surplus'
                const isPreserve = r.rule_code === 'RULE_D' || r.gap_type === 'preserve'

                const category = r.category || (isRiskAlert ? 'Behavioural risk alert' : isShortfall ? 'Funding required' : 'Potential investment')
                const severityLabel = r.severity === 'high' ? 'High priority' : r.severity === 'surplus' ? 'Surplus' : r.severity === 'monitor' ? 'Monitor' : 'Medium priority'

                return (
                  <article
                    key={r.id}
                    className={`rec-card ${r.severity || 'medium'} ${r.rule_code || ''}`}
                  >
                    <div className="rec-card-top">
                      <span className="rec-card-category">{category}</span>
                      <span className={`rec-chip chip-${r.severity || 'normal'}`}>
                        {severityLabel}
                      </span>
                    </div>

                    <div className="rec-card-amount">
                      {formatCurrency(r.amount, currency)}
                    </div>

                    <p className="rec-card-headline">
                      {/* Preserving r.action_text so users and tests get exact text */}
                      <strong>{r.action_text}</strong>
                    </p>

                    {r.detailed_action && r.detailed_action !== r.action_text && (
                      <p className="rec-card-desc">{r.detailed_action}</p>
                    )}

                    <div className="rec-card-reason-box">
                      <strong>Reason:</strong> {r.reason || 'AI-adjusted liabilities exceed assets.'}
                    </div>

                    <div className="rec-card-badges">
                      <span className="badge">{r.currency}</span>
                      <span className="badge">{r.location}</span>
                      <span className="badge">{r.bucket}</span>
                      {r.rule_code && <span className="badge rule-badge">{r.rule_code}</span>}
                    </div>

                    <div className="rec-card-gaps-row">
                      <span className="gap-item">
                        AI gap: <strong className={r.ai_gap < 0 ? 'neg' : 'pos'}>{formatCurrency(r.ai_gap, currency)}</strong>
                      </span>
                      <span className="gap-item">
                        Deterministic: <strong className={r.deterministic_gap < 0 ? 'neg' : 'pos'}>{formatCurrency(r.deterministic_gap, currency)}</strong>
                      </span>
                    </div>

                    {r.rationale && (
                      <p className="muted small" style={{ marginTop: '8px', borderTop: '1px solid var(--line)', paddingTop: '8px' }}>
                        {r.rationale}
                      </p>
                    )}
                  </article>
                )
              })}
            </div>
          )}
        </>
      )}
    </>
  )
}
