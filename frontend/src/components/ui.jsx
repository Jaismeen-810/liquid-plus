export function PageHead({ title, note, children }) {
  return (
    <div className="pagehead">
      <div>
        <h1>{title}</h1>
        {note && <p>{note}</p>}
      </div>
      {children && <div className="actions">{children}</div>}
    </div>
  )
}

export function Status({ loading, error, label = 'Loading' }) {
  if (error) return <p className="error">{error.message}</p>
  if (loading) return <p className="muted">{label}…</p>
  return null
}

export function Money({ value, className = '' }) {
  const cls = value < 0 ? 'neg' : value > 0 ? 'pos' : ''
  const text = value === null || value === undefined ? '–' : new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
  return <span className={`num ${cls} ${className}`}>{text}</span>
}

export function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="pager">
      <span>{total.toLocaleString()} transactions</span>
      <button disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
      <span>Page {page} of {pages}</span>
      <button disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
    </div>
  )
}
