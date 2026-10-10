import { useState } from 'react'
import { api, useFetch } from '../api'
import { useFilters } from '../filters'
import { amount, pct } from '../format'
import Rationale from './Rationale'
import { Pager, Status } from './ui'

const PAGE_SIZE = 25

export default function Transactions({ view, bucket }) {
  const { params, currency } = useFilters()
  const [page, setPage] = useState(1)
  const [book, setBook] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState(view === 'ai' ? 'p_early' : 'maturity_cashflow')
  const [openId, setOpenId] = useState(null)
  const ai = view === 'ai'

  const query = { ...params, currency, bucket, book: book || undefined, search: search || undefined, sort_by: sort, page, page_size: PAGE_SIZE }
  const { data, loading, error } = useFetch(`/api/ladder/${view}/transactions`, query)
  const reset = fn => value => { fn(value); setPage(1) }

  return (
    <section>
      <div className="sectionhead">
        <h2>Transactions in {bucket} <span className="muted">({currency})</span></h2>
        <form className="inline" onSubmit={e => { e.preventDefault(); reset(setSearch)(e.target.q.value.trim()) }}>
          <select value={book} onChange={e => reset(setBook)(e.target.value)}>
            <option value="">Assets and liabilities</option>
            <option value="asset">Assets only</option>
            <option value="liability">Liabilities only</option>
          </select>
          <select value={sort} onChange={e => reset(setSort)(e.target.value)}>
            <option value="maturity_cashflow">Largest cash flow</option>
            <option value="contractual_maturity">Earliest maturity</option>
            {ai && <option value="p_early">Highest exit probability</option>}
          </select>
          <input name="q" placeholder="Transaction or customer ID" defaultValue={search} />
          <button type="submit">Search</button>
          <button type="button" onClick={() => api.download('/api/export/transactions', { ...params, currency, view, bucket, book: book || undefined })}>
            Export Excel
          </button>
        </form>
      </div>

      <Status loading={loading && !data} error={error} />
      {data && (
        <>
          <div className="scroll">
            <table className={`grid ${ai ? 'clickable' : ''}`}>
              <thead>
                <tr>
                  <th>Transaction</th><th>Type</th><th>Location</th><th>Segment</th>
                  <th className="r">Principal</th><th className="r">Interest</th><th className="r">Cash flow</th>
                  <th>Contractual</th>
                  {ai && <><th>Adjusted</th><th className="r">Early exit</th></>}
                </tr>
              </thead>
              <tbody>
                {data.items.map(t => (
                  <tr key={t.transaction_id} onClick={ai ? () => setOpenId(t.transaction_id) : undefined} className={openId === t.transaction_id ? 'on' : ''}>
                    <td className="mono">{t.transaction_id}</td>
                    <td>{t.book === 'asset' ? 'Loan' : 'Deposit'}<small>{t.product_type}</small></td>
                    <td>{t.location}</td>
                    <td>{t.customer_segment}</td>
                    <td className="r num">{amount(t.principal)}</td>
                    <td className="r num">{amount(t.interest_amount)}</td>
                    <td className="r num">{amount(t.maturity_cashflow)}</td>
                    <td className="num">{t.contractual_maturity}</td>
                    {ai && (
                      <>
                        <td className="num">{t.adjusted_maturity}{t.days_pulled_forward > 0 && <small>{t.days_pulled_forward} days earlier</small>}</td>
                        <td className="r num">{pct(t.p_early)}<small>{t.risk_level?.toLowerCase()} risk</small></td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
        </>
      )}
      {openId && <Rationale id={openId} onClose={() => setOpenId(null)} />}
    </section>
  )
}
