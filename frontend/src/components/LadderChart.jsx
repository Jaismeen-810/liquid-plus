import { Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { COLORS, money } from '../format'

export default function LadderChart({ rows, selected, onSelect, currency }) {
  const pick = state => state?.activeLabel && onSelect(state.activeLabel)
  const dim = bucket => (selected && selected !== bucket ? 0.35 : 1)

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={rows} onClick={pick} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid vertical={false} stroke="#E6E9EE" />
          <XAxis dataKey="bucket" tickLine={false} axisLine={{ stroke: '#C9CFD8' }} />
          <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={64} />
          <Tooltip formatter={(v, name) => [`${currency} ${money(v)}`, name]} cursor={{ fill: '#F2F4F7' }} />
          <Legend iconType="square" iconSize={10} />
          <ReferenceLine y={0} stroke="#8A94A3" />
          <Bar dataKey="assets" name="Assets (inflows)" fill={COLORS.asset} maxBarSize={44}>
            {rows.map(r => <Cell key={r.bucket} fillOpacity={dim(r.bucket)} cursor="pointer" />)}
          </Bar>
          <Bar dataKey="liabilities" name="Liabilities (outflows)" fill={COLORS.liability} maxBarSize={44}>
            {rows.map(r => <Cell key={r.bucket} fillOpacity={dim(r.bucket)} cursor="pointer" />)}
          </Bar>
          <Line dataKey="net_gap" name="Net gap" stroke={COLORS.gap} strokeWidth={2} dot={{ r: 4, fill: COLORS.gap }} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="hint">Click a bucket to see its transactions.</p>
    </div>
  )
}
