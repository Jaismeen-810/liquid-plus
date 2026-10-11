import { useMemo, useState } from 'react'
import { api, useFetch } from '../api'
import { useFilters } from '../filters'
import { CURRENCIES, formatCurrency } from '../format'
import { PageHead, Status } from '../components/ui'
import RecommendationList from '../components/RecommendationList'

export default function Recommendations() {
  const { params, location, currency: selectedCurrency } = useFilters()
  const [currency, setCurrency] = useState(selectedCurrency)
  const [severity, setSeverity] = useState('')
  const [ruleCode, setRuleCode] = useState('')

  const activeFilters = useMemo(() => ({
    ...params,
    currency: currency || undefined,
  }), [params, currency])

  // Fetch summary metrics
  const { data: allRecs, loading, error } = useFetch('/api/recommendations', activeFilters)

  // Calculate KPI stats
  const stats = useMemo(() => {
    const list = allRecs || []
    const fundingNeeded = list
      .filter(r => r.rule_code === 'RULE_A' || r.gap_type === 'shortfall')
      .reduce((sum, r) => sum + (r.amount || 0), 0)

    const investableSurplus = list
      .filter(r => r.rule_code === 'RULE_B' || r.gap_type === 'surplus')
      .reduce((sum, r) => sum + (r.investable_surplus || r.amount || 0), 0)

    const riskAlerts = list.filter(r => r.rule_code === 'RULE_C' || r.gap_type === 'risk_alert').length

    const preservedFunds = list
      .filter(r => r.rule_code === 'RULE_D' || r.gap_type === 'preserve')
      .reduce((sum, r) => sum + (r.reserved_amount || 0), 0)

    // Filter count matching active severity & ruleCode
    const displayedCount = list.filter(r => {
      if (severity && r.severity !== severity) return false
      if (ruleCode && r.rule_code !== ruleCode) return false
      return true
    }).length

    return {
      total: list.length,
      displayedCount,
      fundingNeeded,
      investableSurplus,
      riskAlerts,
      preservedFunds,
    }
  }, [allRecs, severity, ruleCode])

  // amounts in different currencies can't be added up, so totals need one currency
  const total = value => (currency ? formatCurrency(value, currency) : '–')

  return (
    <div className="recommendations-dashboard">
      <PageHead
        title="Treasury Recommendations"
        note={`Actions from the AI-adjusted gap ladder · ${currency || 'All currencies'} · ${location || 'All locations'} · as of ${params.run_date}`}
      >
        <select
          value={currency}
          onChange={e => setCurrency(e.target.value)}
          aria-label="Currency"
        >
          <option value="">All currencies</option>
          {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <select
          value={severity}
          onChange={e => setSeverity(e.target.value)}
          aria-label="Severity"
        >
          <option value="">All severities</option>
          <option value="high">High priority</option>
          <option value="surplus">Surplus</option>
          <option value="monitor">Monitor</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        <button
          type="button"
          onClick={() => api.download('/api/export/recommendations', { ...activeFilters, format: 'xlsx' })}
        >
          Export Excel
        </button>
        <button
          type="button"
          onClick={() => api.download('/api/export/recommendations', { ...activeFilters, format: 'pdf' })}
        >
          Export PDF
        </button>
      </PageHead>

      {/* KPI Overview Summary Banner */}
      <section className="rec-kpi-bar" aria-label="Treasury liquidity summary">
        <div className="kpi-card kpi-funding">
          <small>Rule A · Shortfall</small>
          <h3>Funding required</h3>
          <p className="kpi-value neg">{total(stats.fundingNeeded)}</p>
          <span className="kpi-sub">Wholesale / repo borrowing</span>
        </div>

        <div className="kpi-card kpi-surplus">
          <small>Rule B · Surplus</small>
          <h3>Potential investment</h3>
          <p className="kpi-value pos">{total(stats.investableSurplus)}</p>
          <span className="kpi-sub">Deployable after regulatory buffer</span>
        </div>

        <div className="kpi-card kpi-risk">
          <small>Rule C · Behavioral</small>
          <h3>Risk alerts</h3>
          <p className="kpi-value warn">{stats.riskAlerts}</p>
          <span className="kpi-sub">Early withdrawal warnings</span>
        </div>

        <div className="kpi-card kpi-preserve">
          <small>Rule D · Preservation</small>
          <h3>Reserved liquidity</h3>
          <p className="kpi-value">{total(stats.preservedFunds)}</p>
          <span className="kpi-sub">Reserved for upcoming deficits</span>
        </div>
      </section>

      {!currency && <p className="hint">Pick a currency to see totals; amounts in different currencies are not added together.</p>}

      {/* Rule Selection and Insights Counter */}
      <div className="rec-toolbar">
        <div className="insights-count-badge">
          <strong>{stats.displayedCount} insights</strong>
          <span className="muted">for selected criteria</span>
        </div>

        <div className="rule-filter-tabs">
          <button
            type="button"
            className={`rule-tab-btn ${!ruleCode ? 'active' : ''}`}
            onClick={() => setRuleCode('')}
          >
            All rules
          </button>
          <button
            type="button"
            className={`rule-tab-btn ${ruleCode === 'RULE_A' ? 'active' : ''}`}
            onClick={() => setRuleCode('RULE_A')}
          >
            Rule A: Raise funding
          </button>
          <button
            type="button"
            className={`rule-tab-btn ${ruleCode === 'RULE_B' ? 'active' : ''}`}
            onClick={() => setRuleCode('RULE_B')}
          >
            Rule B: Deploy surplus
          </button>
          <button
            type="button"
            className={`rule-tab-btn ${ruleCode === 'RULE_C' ? 'active' : ''}`}
            onClick={() => setRuleCode('RULE_C')}
          >
            Rule C: Early withdrawals
          </button>
          <button
            type="button"
            className={`rule-tab-btn ${ruleCode === 'RULE_D' ? 'active' : ''}`}
            onClick={() => setRuleCode('RULE_D')}
          >
            Rule D: Preserve liquidity
          </button>
        </div>
      </div>

      {/* Actionable Cards Grid */}
      <RecommendationList
        filters={activeFilters}
        severity={severity}
        ruleCode={ruleCode}
        viewMode="cards"
      />
    </div>
  )
}
