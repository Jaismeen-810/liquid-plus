import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { useFilters } from '../filters'
import { CURRENCIES, LOCATIONS } from '../format'

const LINKS = [
  ['/ladder', 'Deterministic ladder'],
  ['/ai', 'AI-adjusted ladder'],
  ['/compare', 'Comparison'],
  ['/what-if', 'What-if'],
  ['/actions', 'Recommendations'],
  ['/history', 'Behavioral analytics'],
]

export default function Layout() {
  const { user, logout } = useAuth()
  const f = useFilters()

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Liquid<b>+</b></span>
        <div className="filters">
          <label>
            Run date
            <select value={f.runDate} onChange={e => f.setRunDate(e.target.value)} disabled={!f.runDates.length}>
              {!f.runDates.length && <option value="">No data</option>}
              {f.runDates.map(d => <option key={d.run_date} value={d.run_date}>{d.run_date}</option>)}
            </select>
          </label>
          <label>
            Location
            <select value={f.location} onChange={e => f.setLocation(e.target.value)} disabled={!f.isSupport}>
              {f.isSupport && <option value="">All locations</option>}
              {(f.isSupport ? LOCATIONS : [user.location]).map(l => <option key={l}>{l}</option>)}
            </select>
          </label>
          <label>
            Currency
            <select value={f.currency} onChange={e => f.setCurrency(e.target.value)}>
              {CURRENCIES.map(c => <option key={c}>{c}</option>)}
            </select>
          </label>
        </div>
        <div className="who">
          <span>{user.full_name || user.username}</span>
          <small>{user.role === 'SUPPORT' ? 'Support, all locations' : user.location}</small>
          <button className="link" onClick={logout}>Log out</button>
        </div>
      </header>

      <nav className="sidenav">
        {LINKS.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        {f.isSupport && <NavLink to="/data" className="sep">Data and models</NavLink>}
      </nav>

      <main className="content">
        {!f.datesLoading && !f.runDates.length ? <NoData support={f.isSupport} /> : f.runDate && <Outlet />}
      </main>
    </div>
  )
}

function NoData({ support }) {
  if (support) return <Outlet />
  return (
    <div className="empty-state">
      <h1>No positions loaded yet</h1>
      <p>Ask a support user to upload the asset and liability books.</p>
    </div>
  )
}
