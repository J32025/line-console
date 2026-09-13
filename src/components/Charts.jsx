// ชุดกราฟ/การ์ดที่ใช้ร่วมกันหลายหน้า (Dashboard, Behavior ฯลฯ) — ปาเลตต์เดียวกันทั้งระบบ
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'

/* ปาเลตต์หมวดหมู่ — ลำดับคงที่ ไม่วนซ้ำ */
export const CAT = ['#06c755', '#2563eb', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d', '#64748b']
export const AXIS = { fontSize: 11, fill: 'var(--muted)' }
export const GRID = 'var(--border)'
export const mmdd = (d) => (d || '').slice(5)
export const nf = (n) => (n == null ? '–' : Number(n).toLocaleString('th-TH'))
export const baht = (n) => (n == null ? '–' : '฿' + Number(n).toLocaleString('th-TH'))
export const dtf = (s) => new Date(s).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' })
export const ttStyle = { background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, boxShadow: 'var(--shadow)' }

export function Card({ title, sub, children, right }) {
  return (
    <section className="card">
      {title && (
        <div className="row spread" style={{ alignItems: 'baseline' }}>
          <h3 style={{ margin: '0 0 2px' }}>{title}</h3>
          {right}
        </div>
      )}
      {sub && <p className="muted xs" style={{ margin: '0 0 8px' }}>{sub}</p>}
      {children}
    </section>
  )
}

export const Empty = () => <p className="muted sm center" style={{ padding: '18px 0', minHeight: 'auto' }}>ยังไม่มีข้อมูล</p>

export function TimeArea({ data, keys, height = 210 }) {
  if (!data?.length) return <Empty />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <defs>{keys.map((s) => (
          <linearGradient key={s.k} id={`g-${s.k}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
          </linearGradient>
        ))}</defs>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="day" tickFormatter={mmdd} tick={AXIS} minTickGap={24} />
        <YAxis tick={AXIS} width={44} allowDecimals={false} />
        <Tooltip contentStyle={ttStyle} labelFormatter={(l) => `วันที่ ${l}`} />
        {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {keys.map((s) => (
          <Area key={s.k} type="monotone" dataKey={s.k} name={s.name} stroke={s.color}
                strokeWidth={2} fill={`url(#g-${s.k})`} dot={false} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function StackBars({ data, keys, height = 210 }) {
  if (!data?.length) return <Empty />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="day" tickFormatter={mmdd} tick={AXIS} minTickGap={24} />
        <YAxis tick={AXIS} width={44} allowDecimals={false} />
        <Tooltip contentStyle={ttStyle} labelFormatter={(l) => `วันที่ ${l}`} />
        {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {keys.map((s, i) => (
          <Bar key={s.k} dataKey={s.k} name={s.name} stackId="a" fill={s.color}
               radius={i === keys.length - 1 ? [3, 3, 0, 0] : 0} maxBarSize={26} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function BarList({ rows, labelKey, valueKey, fmt = nf, color = CAT[1] }) {
  if (!rows?.length) return <Empty />
  const max = Math.max(...rows.map((r) => r[valueKey] || 0), 1)
  return (
    <div className="barlist">
      {rows.map((r, i) => (
        <div key={i} className="barlist-row">
          <span className="barlist-label" title={r[labelKey]}>{r[labelKey]}</span>
          <span className="barlist-track">
            <span className="barlist-fill" style={{
              width: `${((r[valueKey] || 0) / max) * 100}%`,
              background: Array.isArray(color) ? color[i % color.length] : color,
            }} />
          </span>
          <span className="barlist-val">{fmt(r[valueKey])}</span>
        </div>
      ))}
    </div>
  )
}

export function Donut({ rows, nameKey, valueKey, colors = CAT, height = 190 }) {
  const data = (rows || []).filter((r) => (r[valueKey] || 0) > 0)
  if (!data.length) return <Empty />
  const total = data.reduce((s, r) => s + (r[valueKey] || 0), 0)
  return (
    <div className="row" style={{ alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <ResponsiveContainer width={height} height={height}>
        <PieChart>
          <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius="58%" outerRadius="92%"
               paddingAngle={2} stroke="var(--panel)" strokeWidth={2}>
            {data.map((r, i) => <Cell key={i} fill={typeof colors === 'function' ? colors(r) : colors[i % colors.length]} />)}
          </Pie>
          <Tooltip contentStyle={ttStyle} formatter={(v) => nf(v)} />
        </PieChart>
      </ResponsiveContainer>
      <div className="donut-legend">
        {data.map((r, i) => (
          <div key={i} className="row" style={{ gap: 6, fontSize: 12 }}>
            <span className="dot-sq" style={{ background: typeof colors === 'function' ? colors(r) : colors[i % colors.length] }} />
            <span style={{ flex: 1 }}>{r[nameKey]}</span>
            <b>{nf(r[valueKey])}</b><span className="muted">{Math.round((r[valueKey] / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
