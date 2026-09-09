import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { api } from '../lib/api.js'
import { SkeletonStats, SkeletonRows, InlineSpinner, Stat, useToast } from '../lib/ui.jsx'

/* ปาเลตต์หมวดหมู่ — ลำดับคงที่ ไม่วนซ้ำ */
const CAT = ['#06c755', '#2563eb', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d', '#64748b']
const ST = { verified: '#06c755', review: '#d97706', rejected: '#e5484d', new: '#2563eb' }
const AXIS = { fontSize: 11, fill: 'var(--muted)' }
const GRID = 'var(--border)'
const mmdd = (d) => (d || '').slice(5)
const nf = (n) => (n == null ? '–' : Number(n).toLocaleString('th-TH'))
const baht = (n) => (n == null ? '–' : '฿' + Number(n).toLocaleString('th-TH'))

const TABS = [
  ['overview', 'ภาพรวม'],
  ['people', 'ผู้ใช้'],
  ['revenue', 'รายได้ / สลิป'],
  ['messages', 'ข้อความ'],
  ['bot', 'บอท & แคมเปญ'],
  ['system', 'ระบบ'],
]

export default function Dashboard() {
  const t = useToast()
  const nav = useNavigate()
  const [range, setRange] = useState(30)
  const [tab, setTab] = useState('overview')
  const [d, setD] = useState(null)
  const [a, setA] = useState(null)
  const [err, setErr] = useState('')

  const load = (r = range) => {
    setD(null); setA(null); setErr('')
    api.dashboard(r).then(setD).catch((e) => setErr(e.message))
    api.dashboardAnalytics(r).then(setA).catch(() => {})
  }
  useEffect(() => { load(range) }, [range]) // eslint-disable-line

  if (err) return <p className="err">{err}</p>

  return (
    <div className="dash">
      <div className="row spread wrap" style={{ alignItems: 'center', marginBottom: 4 }}>
        <h1 style={{ margin: 0 }}>แดชบอร์ด</h1>
        <div className="row wrap" style={{ gap: 6 }}>
          {[7, 14, 30, 60, 90].map((r) => (
            <button key={r} className={range === r ? 'sm primary' : 'sm'} onClick={() => setRange(r)}>{r} วัน</button>
          ))}
          <button className="sm" onClick={() => load()}>↻</button>
        </div>
      </div>
      {d && (
        <div className="muted xs" style={{ marginBottom: 10 }}>
          อัปเดต {new Date(d.generated_at).toLocaleString('th-TH')} · deploy <code>{d.commit}</code>
        </div>
      )}

      <div className="dash-tabs">
        {TABS.map(([k, l]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {!d ? (
        <>
          <SkeletonStats />
          <div className="card"><SkeletonRows rows={6} cols={2} /></div>
          <div className="loading-text center"><InlineSpinner />กำลังโหลดแดชบอร์ด…</div>
        </>
      ) : (
        <>
          {tab === 'overview' && <Overview d={d} a={a} nav={nav} />}
          {tab === 'people' && <People d={d} a={a} />}
          {tab === 'revenue' && <Revenue d={d} a={a} nav={nav} />}
          {tab === 'messages' && <Messages d={d} a={a} />}
          {tab === 'bot' && <Bot d={d} a={a} />}
          {tab === 'system' && <System d={d} a={a} />}
        </>
      )}
    </div>
  )
}

/* ---------- ชิ้นส่วนกราฟ ---------- */

function Card({ title, sub, children, right }) {
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

function TimeArea({ data, keys, height = 220 }) {
  // keys: [{ k, name, color }]
  if (!data?.length) return <Empty />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <defs>
          {keys.map((s) => (
            <linearGradient key={s.k} id={`g-${s.k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
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

function StackBars({ data, keys, height = 220 }) {
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

function BarList({ rows, labelKey, valueKey, fmt = nf, color = CAT[1], max: maxProp }) {
  if (!rows?.length) return <Empty />
  const max = maxProp || Math.max(...rows.map((r) => r[valueKey] || 0), 1)
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

function Donut({ rows, nameKey, valueKey, colors = CAT, height = 200 }) {
  const data = (rows || []).filter((r) => (r[valueKey] || 0) > 0)
  if (!data.length) return <Empty />
  const total = data.reduce((s, r) => s + (r[valueKey] || 0), 0)
  return (
    <div className="row" style={{ alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <ResponsiveContainer width={height} height={height}>
        <PieChart>
          <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius="58%" outerRadius="92%"
               paddingAngle={2} stroke="var(--panel)" strokeWidth={2}>
            {data.map((r, i) => (
              <Cell key={i} fill={typeof colors === 'function' ? colors(r) : colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={ttStyle} formatter={(v) => nf(v)} />
        </PieChart>
      </ResponsiveContainer>
      <div className="donut-legend">
        {data.map((r, i) => (
          <div key={i} className="row" style={{ gap: 6, fontSize: 12 }}>
            <span className="dot-sq" style={{ background: typeof colors === 'function' ? colors(r) : colors[i % colors.length] }} />
            <span style={{ flex: 1 }}>{r[nameKey]}</span>
            <b>{nf(r[valueKey])}</b>
            <span className="muted">{Math.round((r[valueKey] / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Funnel({ steps }) {
  if (!steps?.length) return <Empty />
  const max = steps[0].count || 1
  return (
    <div className="barlist">
      {steps.map((s, i) => {
        const prev = i ? steps[i - 1].count : s.count
        const drop = prev ? Math.round((s.count / prev) * 100) : 100
        return (
          <div key={i} className="barlist-row">
            <span className="barlist-label">{s.step}</span>
            <span className="barlist-track">
              <span className="barlist-fill" style={{ width: `${(s.count / max) * 100}%`, background: CAT[i % CAT.length] }} />
            </span>
            <span className="barlist-val">{nf(s.count)} {i > 0 && <span className="muted">({drop}%)</span>}</span>
          </div>
        )
      })}
    </div>
  )
}

function Heatmap({ grid }) {
  const DOW = ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา']
  const flat = (grid || []).flat()
  const max = Math.max(...flat, 1)
  if (!flat.some((x) => x > 0)) return <Empty />
  return (
    <div className="heatmap">
      <div className="heat-hours">
        <span />{[0, 3, 6, 9, 12, 15, 18, 21].map((h) => <span key={h}>{h}</span>)}
      </div>
      {(grid || []).map((row, di) => (
        <div key={di} className="heat-row">
          <span className="heat-dow">{DOW[di]}</span>
          {row.map((v, hi) => (
            <span key={hi} className="heat-cell" title={`${DOW[di]} ${hi}:00 — ${v} ข้อความ`}
                  style={{ background: v ? `rgba(6,199,85,${0.12 + (v / max) * 0.8})` : 'var(--panel-2,#f1f3f6)' }} />
          ))}
        </div>
      ))}
    </div>
  )
}

const ttStyle = {
  background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 8,
  fontSize: 12, boxShadow: 'var(--shadow)',
}
const Empty = () => <p className="muted sm center" style={{ padding: '20px 0' }}>ยังไม่มีข้อมูล</p>

/* ---------- แท็บ: ภาพรวม ---------- */
function Overview({ d, a, nav }) {
  const s = d.slips, sys = d.system
  return (
    <>
      <div className="grid stats">
        <Stat label="ผู้ติดตาม" value={nf(d.users.following)}
              sub={`${d.users.follow_rate}% ของทั้งหมด · +${d.growth_totals.net} ช่วงนี้`} />
        <Stat label="แอคทีฟ 30 วัน" value={nf(d.users.active_30d)}
              sub={`${d.users.active_rate}% ของผู้ติดตาม`} />
        <Stat label="สลิปรอตรวจ" value={nf(s.pending_action)}
              sub={s.pending_action ? 'ต้องดำเนินการ' : 'เคลียร์หมดแล้ว'} />
        <Stat label="รายได้ยืนยันแล้ว" value={baht(s.revenue_verified)}
              sub={`สัปดาห์นี้ ${baht(s.revenue_week)}`} />
        <Stat label="โควตาข้อความ"
              value={sys.quota_pct != null ? sys.quota_pct + '%' : nf(sys.quota_used)}
              sub={`${nf(sys.quota_used)} / ${nf(sys.quota_limit)}`} />
        <Stat label="แชทค้างตอบ" value={nf(d.users.unread_threads)}
              sub={sys.errors_24h ? `⚠ error 24 ชม. ${sys.errors_24h}` : 'ระบบปกติ'} />
      </div>

      <Card title="Quick actions">
        <div className="row wrap">
          <button className="sm primary" onClick={() => nav('/messaging')}>ส่งข้อความ</button>
          <button className="sm" onClick={() => nav('/slips')}>ตรวจสลิป {s.pending_action ? `(${s.pending_action})` : ''}</button>
          <button className="sm" onClick={() => nav('/inbox')}>กล่องข้อความ {d.users.unread_threads ? `(${d.users.unread_threads})` : ''}</button>
          <button className="sm" onClick={() => nav('/richmenus')}>Rich Menu</button>
          <button className="sm" onClick={() => nav('/stats')}>สถิติ LINE</button>
        </div>
      </Card>

      <div className="grid two">
        <Card title="การเติบโตผู้ติดตาม" sub={`${d.range_days} วัน · +${d.growth_totals.follow} / -${d.growth_totals.unfollow} = สุทธิ ${d.growth_totals.net >= 0 ? '+' : ''}${d.growth_totals.net}`}>
          <StackBars data={d.growth} keys={[
            { k: 'follow', name: 'เพิ่มเพื่อน', color: ST.verified },
            { k: 'unfollow', name: 'บล็อก/ลบ', color: ST.rejected },
          ]} />
        </Card>
        <Card title="ผู้ติดตามสะสม (สุทธิ)" sub="เทียบต้นช่วง">
          <TimeArea data={d.growth} keys={[{ k: 'cumulative', name: 'สุทธิสะสม', color: CAT[1] }]} />
        </Card>
      </div>

      <div className="grid two">
        <Card title="เส้นทางลูกค้า (Funnel)" sub="ผู้ใช้ → ยืนยันชำระเงิน">
          <Funnel steps={a?.funnel} />
        </Card>
        <Card title="สลิปแยกสถานะ" sub={`ทั้งหมด ${nf(s.total)} · วันนี้ ${nf(s.today)}`}>
          <Donut rows={[
            { k: 'verified', name: 'ผ่าน', v: s.by_status.verified },
            { k: 'review', name: 'ต้องตรวจเอง', v: s.by_status.review },
            { k: 'new', name: 'ใหม่', v: s.by_status.new },
            { k: 'rejected', name: 'ไม่ผ่าน', v: s.by_status.rejected },
          ]} nameKey="name" valueKey="v" colors={(r) => ST[r.k]} />
        </Card>
      </div>

      <Card title="ปฏิบัติการล่าสุด">
        <OpsList ops={d.recent_operations} />
      </Card>
    </>
  )
}

/* ---------- แท็บ: ผู้ใช้ ---------- */
function People({ d, a }) {
  const u = d.users
  return (
    <>
      <div className="grid stats">
        <Stat label="ผู้ใช้ในระบบ" value={nf(u.total)} />
        <Stat label="กำลังติดตาม" value={nf(u.following)} sub={`${u.follow_rate}%`} />
        <Stat label="เลิกติดตาม" value={nf(u.not_following)} />
        <Stat label="ใหม่ 7 วัน" value={nf(u.new_7d)} sub={`30 วัน ${nf(u.new_30d)}`} />
        <Stat label="มี Rich Menu" value={nf(u.with_menu)} sub={`ไม่มี ${nf(u.no_menu)}`} />
        <Stat label="แอคทีฟ 7 วัน" value={nf(u.active_7d)} sub={`30 วัน ${nf(u.active_30d)}`} />
      </div>

      <Card title="ผู้ใช้ใหม่ / วัน" sub={`${d.range_days} วันล่าสุด (จาก first_followed_at)`}>
        <StackBars data={d.new_daily} keys={[{ k: 'count', name: 'ผู้ใช้ใหม่', color: CAT[0] }]} />
      </Card>

      <div className="grid two">
        <Card title="follow / unfollow รายวัน">
          <StackBars data={d.growth} keys={[
            { k: 'follow', name: 'เพิ่ม', color: ST.verified },
            { k: 'unfollow', name: 'ออก', color: ST.rejected },
          ]} />
        </Card>
        <Card title="แหล่งที่มาผู้ใช้">
          <BarList rows={d.users.source_breakdown} labelKey="source" valueKey="count" color={CAT} />
        </Card>
      </div>

      <Card title="การกระจาย Rich Menu" sub="เฉพาะผู้ที่กำลังติดตาม เรียงมาก→น้อย">
        <BarList rows={d.menu_distribution.map((m) => ({ ...m, name: m.name + (m.is_default ? ' (default)' : '') }))}
                 labelKey="name" valueKey="count" color={CAT[3]} />
      </Card>

      {a?.demographic?.genders?.length > 0 && (
        <div className="grid two">
          <Card title="เพศ (LINE insight)">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={a.demographic.genders} margin={{ left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
                <XAxis dataKey="gender" tick={AXIS} /><YAxis tick={AXIS} unit="%" />
                <Tooltip contentStyle={ttStyle} formatter={(v) => v + '%'} />
                <Bar dataKey="percentage" fill={CAT[0]} radius={[3, 3, 0, 0]} maxBarSize={60} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="อายุ (LINE insight)">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={a.demographic.ages} margin={{ left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
                <XAxis dataKey="age" tick={{ ...AXIS, fontSize: 9 }} /><YAxis tick={AXIS} unit="%" />
                <Tooltip contentStyle={ttStyle} formatter={(v) => v + '%'} />
                <Bar dataKey="percentage" fill={CAT[1]} radius={[3, 3, 0, 0]} maxBarSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}

      {a?.history?.length > 1 && (
        <Card title="แนวโน้มผู้ติดตาม (LINE insight)" sub="lag 1-2 วัน">
          <TimeArea data={a.history} keys={[
            { k: 'followers', name: 'ผู้ติดตาม', color: CAT[0] },
            { k: 'targeted_reaches', name: 'เข้าถึงได้', color: CAT[1] },
            { k: 'blocks', name: 'บล็อก', color: ST.rejected },
          ]} height={240} />
        </Card>
      )}
    </>
  )
}

/* ---------- แท็บ: รายได้ / สลิป ---------- */
function Revenue({ d, a, nav }) {
  const s = d.slips
  return (
    <>
      <div className="grid stats">
        <Stat label="รายได้ยืนยันแล้ว" value={baht(s.revenue_verified)} />
        <Stat label="สัปดาห์นี้" value={baht(s.revenue_week)} />
        <Stat label="สลิปรอตรวจ" value={nf(s.pending_action)} sub={`ใหม่ ${s.by_status.new} · ตรวจเอง ${s.by_status.review}`} />
        <Stat label="ยืนยันแล้ว" value={nf(s.by_status.verified)} sub={`ไม่ผ่าน ${s.by_status.rejected}`} />
        <Stat label="สลิปวันนี้" value={nf(s.today)} sub={`7 วัน ${nf(s.week)}`} />
        <Stat label="ทั้งหมด" value={nf(s.total)} />
      </div>

      <Card title="สลิปรายวัน" sub={`${d.range_days} วัน`} right={
        <button className="xs primary" onClick={() => nav('/slips')}>เปิดหน้าสลิป</button>
      }>
        <StackBars data={s.daily} keys={[
          { k: 'verified', name: 'ผ่าน', color: ST.verified },
          { k: 'review', name: 'ตรวจเอง', color: ST.review },
          { k: 'new', name: 'ใหม่', color: ST.new },
          { k: 'rejected', name: 'ไม่ผ่าน', color: ST.rejected },
        ]} height={240} />
      </Card>

      <div className="grid two">
        <Card title="แยกตามหลักสูตร" sub="ยอดที่ยืนยันแล้ว">
          <table>
            <thead><tr><th>หลักสูตร</th><th>สลิป</th><th>ยืนยัน</th><th>ยอดเงิน</th></tr></thead>
            <tbody>
              {(s.by_course || []).map((c) => (
                <tr key={c.course}>
                  <td><b>{c.course}</b></td><td>{nf(c.count)}</td><td>{nf(c.verified)}</td>
                  <td>{baht(Math.round(c.amount))}</td>
                </tr>
              ))}
              {!s.by_course?.length && <tr><td colSpan={4} className="muted">ยังไม่มี</td></tr>}
            </tbody>
          </table>
        </Card>
        <Card title="สัดส่วนสถานะสลิป">
          <Donut rows={[
            { k: 'verified', name: 'ผ่าน', v: s.by_status.verified },
            { k: 'review', name: 'ต้องตรวจเอง', v: s.by_status.review },
            { k: 'new', name: 'ใหม่', v: s.by_status.new },
            { k: 'rejected', name: 'ไม่ผ่าน', v: s.by_status.rejected },
          ]} nameKey="name" valueKey="v" colors={(r) => ST[r.k]} />
        </Card>
      </div>

      <Card title="เส้นทางสู่การชำระเงิน">
        <Funnel steps={a?.funnel} />
      </Card>
    </>
  )
}

/* ---------- แท็บ: ข้อความ ---------- */
function Messages({ d, a }) {
  return (
    <>
      <div className="grid stats">
        <Stat label="ข้อความเข้า 7 วัน" value={nf(d.messages.in_7d)} />
        <Stat label="ข้อความออก 7 วัน" value={nf(d.messages.out_7d)} />
        <Stat label="Webhook วันนี้" value={nf(d.system.webhook_today)} />
        <Stat label="แชทค้างตอบ" value={nf(d.users.unread_threads)} />
      </div>

      <Card title="ข้อความเข้า / วัน" sub={`${d.range_days} วัน`}>
        <TimeArea data={a?.messages?.in_daily} keys={[{ k: 'count', name: 'ข้อความเข้า', color: CAT[0] }]} />
      </Card>

      <div className="grid two">
        <Card title="ชนิดข้อความที่เข้ามา">
          <BarList rows={a?.messages?.by_type} labelKey="type" valueKey="count" color={CAT} />
        </Card>
        <Card title="ข้อความออก — แยกที่มา" sub="ตอบอัตโนมัติ vs แอดมิน vs อื่น ๆ">
          <BarList rows={a?.messages?.out_by_source} labelKey="source" valueKey="count" color={CAT[1]} />
        </Card>
      </div>

      <Card title="ช่วงเวลาที่ลูกค้าทักเข้ามา" sub="วัน × ชั่วโมง (เข้ม = เยอะ)">
        <Heatmap grid={a?.messages?.heatmap} />
      </Card>

      <div className="grid two">
        <Card title="Webhook events / วัน">
          <TimeArea data={a?.webhook?.daily} keys={[{ k: 'count', name: 'events', color: CAT[4] }]} />
        </Card>
        <Card title="Webhook แยกชนิด">
          <BarList rows={a?.webhook?.by_type} labelKey="type" valueKey="count" color={CAT} />
        </Card>
      </div>
    </>
  )
}

/* ---------- แท็บ: บอท & แคมเปญ ---------- */
function Bot({ d, a }) {
  const runs = a?.bot?.automation_runs || {}
  return (
    <>
      <div className="grid two">
        <Card title="กฎตอบอัตโนมัติ — ใช้บ่อยสุด">
          <table>
            <thead><tr><th>กฎ</th><th>trigger</th><th>ครั้ง</th></tr></thead>
            <tbody>
              {(a?.bot?.top_rules || []).map((r, i) => (
                <tr key={i} style={{ opacity: r.enabled ? 1 : 0.45 }}>
                  <td>{r.name || '(ไม่มีชื่อ)'}</td><td><span className="chip">{r.trigger}</span></td>
                  <td><b>{nf(r.hits)}</b></td>
                </tr>
              ))}
              {!a?.bot?.top_rules?.length && <tr><td colSpan={3} className="muted">ยังไม่มี</td></tr>}
            </tbody>
          </table>
        </Card>
        <Card title="Postback — ใช้บ่อยสุด">
          <table>
            <thead><tr><th>ปุ่ม</th><th>ครั้ง</th></tr></thead>
            <tbody>
              {(a?.bot?.top_postbacks || []).map((r, i) => (
                <tr key={i} style={{ opacity: r.enabled ? 1 : 0.45 }}>
                  <td title={r.data}>{r.label || r.data}</td><td><b>{nf(r.hits)}</b></td>
                </tr>
              ))}
              {!a?.bot?.top_postbacks?.length && <tr><td colSpan={2} className="muted">ยังไม่มี</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid two">
        <Card title="Automation" sub={`รอส่ง ${nf(runs.pending || 0)} · สำเร็จ ${nf(runs.done || 0)} · ล้มเหลว ${nf(runs.failed || 0)}`}>
          <table>
            <thead><tr><th>ชื่อ</th><th>trigger</th><th>สถานะ</th><th>รัน</th></tr></thead>
            <tbody>
              {(a?.bot?.automations || []).map((r, i) => (
                <tr key={i}>
                  <td>{r.name}</td><td><span className="chip">{r.trigger}</span></td>
                  <td><span className={`chip ${r.enabled ? 'ok' : ''}`}>{r.enabled ? 'เปิด' : 'ปิด'}</span></td>
                  <td>{nf(r.runs)}</td>
                </tr>
              ))}
              {!a?.bot?.automations?.length && <tr><td colSpan={4} className="muted">ยังไม่มี</td></tr>}
            </tbody>
          </table>
        </Card>
        <Card title="งานตั้งเวลา (กำลังจะถึง)">
          <ul className="loglist">
            {(a?.scheduled || []).map((j, i) => (
              <li key={i}>
                <span className="dot" />{j.label || j.kind}
                {j.repeat && <span className="chip xs">{j.repeat}</span>}
                <span className="muted xs"> · {new Date(j.run_at).toLocaleString('th-TH')}</span>
              </li>
            ))}
            {!a?.scheduled?.length && <li className="muted">ไม่มีงานค้าง</li>}
          </ul>
        </Card>
      </div>

      <Card title="ลิงก์สั้น — คลิกรวม" sub={`${d.range_days} วัน`}>
        <TimeArea data={a?.links?.daily} keys={[{ k: 'count', name: 'คลิก', color: CAT[5] }]} height={180} />
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>โค้ด</th><th>ป้าย</th><th>คลิกรวม</th></tr></thead>
          <tbody>
            {(a?.links?.top || []).map((l) => (
              <tr key={l.code}><td><code>{l.code}</code></td><td>{l.label || '–'}</td><td><b>{nf(l.clicks)}</b></td></tr>
            ))}
            {!a?.links?.top?.length && <tr><td colSpan={3} className="muted">ยังไม่มีลิงก์</td></tr>}
          </tbody>
        </table>
      </Card>
    </>
  )
}

/* ---------- แท็บ: ระบบ ---------- */
function System({ d, a }) {
  const sys = d.system
  return (
    <>
      <div className="grid stats">
        <Stat label="โควตาข้อความ" value={sys.quota_pct != null ? sys.quota_pct + '%' : '–'}
              sub={`${nf(sys.quota_used)} / ${nf(sys.quota_limit)}`} />
        <Stat label="คาดใช้ทั้งเดือน" value={nf(sys.quota_projected)}
              sub={sys.quota_limit && sys.quota_projected > sys.quota_limit ? '⚠ เกินโควตา' : 'อยู่ในเกณฑ์'} />
        <Stat label="Error 24 ชม." value={nf(sys.errors_24h)} />
        <Stat label="Automation ค้างส่ง" value={nf(sys.automations_pending)} />
      </div>

      <Card title="โควตาข้อความเดือนนี้">
        <div className="quota-bar">
          <span className="quota-fill" style={{
            width: `${Math.min(sys.quota_pct || 0, 100)}%`,
            background: (sys.quota_pct || 0) > 85 ? ST.rejected : (sys.quota_pct || 0) > 60 ? ST.review : ST.verified,
          }} />
        </div>
        <div className="row spread muted xs" style={{ marginTop: 4 }}>
          <span>ใช้ {nf(sys.quota_used)}</span>
          <span>คาด {nf(sys.quota_projected)} / เพดาน {nf(sys.quota_limit)}</span>
        </div>
      </Card>

      <div className="grid two">
        <Card title="สถานะ Cron">
          <ul className="loglist">
            {(sys.cron || []).map((c, i) => (
              <li key={i}>
                <span className={`dot ${c.status === 'ok' ? 'ok' : c.status || ''}`} />
                <code>{c.job}</code>
                <span className="muted xs"> · {new Date(c.last_run).toLocaleString('th-TH')}</span>
              </li>
            ))}
            {!sys.cron?.length && <li className="muted">ยังไม่มี log</li>}
          </ul>
        </Card>
        <Card title="ขนาดข้อมูล">
          <BarList rows={Object.entries(sys.db_rows || {}).map(([k, v]) => ({ k, v }))}
                   labelKey="k" valueKey="v" color={CAT[7]} />
        </Card>
      </div>

      <Card title="Webhook events / วัน">
        <TimeArea data={a?.webhook?.daily} keys={[{ k: 'count', name: 'events', color: CAT[4] }]} height={180} />
      </Card>

      <div className="grid two">
        <Card title="ปฏิบัติการล่าสุด"><OpsList ops={d.recent_operations} /></Card>
        <Card title="การส่งข้อความล่าสุด">
          <table>
            <thead><tr><th>ชนิด</th><th>ปลายทาง</th><th>สถานะ</th><th>เวลา</th></tr></thead>
            <tbody>
              {(d.recent_broadcasts || []).map((b) => (
                <tr key={b.id}>
                  <td>{b.kind}</td><td>{nf(b.target_count)}</td>
                  <td><span className={`chip ${b.status}`}>{b.status}</span></td>
                  <td className="muted xs">{new Date(b.created_at).toLocaleString('th-TH')}</td>
                </tr>
              ))}
              {!d.recent_broadcasts?.length && <tr><td colSpan={4} className="muted">ยังไม่มี</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  )
}

function OpsList({ ops }) {
  return (
    <ul className="loglist">
      {(ops || []).map((o) => (
        <li key={o.id}>
          <span className={`dot ${o.status}`} />{o.action}
          <span className="muted xs"> · {o.actor?.slice(0, 8) || '–'} · {new Date(o.created_at).toLocaleString('th-TH')}</span>
        </li>
      ))}
      {!ops?.length && <li className="muted">ยังไม่มี</li>}
    </ul>
  )
}
