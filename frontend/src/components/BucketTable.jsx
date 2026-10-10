import { BUCKETS } from '../format'
import { Money } from './ui'

export default function BucketTable({ rows, selected, onSelect }) {
  return (
    <table className="grid clickable">
      <thead>
        <tr><th>Bucket</th><th className="r">Assets</th><th className="r">Liabilities</th><th className="r">Net gap</th><th className="r">Deals</th></tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.bucket} className={selected === r.bucket ? 'on' : ''} onClick={() => onSelect(r.bucket)}>
            <td>{r.bucket}</td>
            <td className="r"><Money value={r.assets} className="plain" /></td>
            <td className="r"><Money value={r.liabilities} className="plain" /></td>
            <td className="r"><Money value={r.net_gap} /></td>
            <td className="r num">{r.asset_count + r.liability_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function GapMatrix({ series }) {
  if (series.length < 2) return null
  return (
    <section>
      <h2>Net gap by location</h2>
      <table className="grid">
        <thead><tr><th>Location</th>{BUCKETS.map(b => <th key={b} className="r">{b}</th>)}</tr></thead>
        <tbody>
          {series.map(s => (
            <tr key={s.location}>
              <td>{s.location}</td>
              {s.buckets.map(b => <td key={b.bucket} className="r"><Money value={b.net_gap} /></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
