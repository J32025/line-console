import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { api } from '../lib/api.js'
import { Spinner, Stat, useToast } from '../lib/ui.jsx'

const todayISO = () => new Date().toISOString().slice(0, 10)
const daysAgoISO = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10)

export default function Stats() {
  const t = useToast()
  const [insight, setInsight] = useState(null)
  const [history, setHistory] = useState([])
  const [quota, setQuota] = useState(null)
  const [follows, setFollows] = useState(null)
  const [funnel, setFunnel] = useState(null)
  const [rev, setRev] = useState(null)
  const [rf, setRf] = useState({ frm: daysAgoISO(30), to: todayISO(), group: 'course' })

  const loadRev = () => api.revenueReport(rf).then(setRev).catch((e) => t.err(e.message))
  useEffect(() => {
    api.quota().then(setQuota).catch(() => {})
    api.insight().then(setInsight).catch((e) => t.err(e.message))
    api.statsHistory(30).then((d) => setHistory([...d.days].reverse())).catch(() => {})
    api.followStats(14).then(setFollows).catch(() => {})
    api.funnel().then(setFunnel).catch(() => {})
    loadRev()
  }, []) // eslint-disable-line

  if (!insight) return <Spinner />
  const f = insight.followers || {}
  const demo = insight.demographic || {}
  const q = quota?.quota?.quota || {}

  return (
    <div>
      <h1>สถิติ <span className="muted sm">({insight.date})</span></h1>

      <div className="grid stats">
        <Stat label="ผู้ติดตาม" value={f.followers?.toLocaleString()} />
        <Stat label="Targeted reach" value={f.targetedReaches?.toLocaleString()} />
        <Stat label="บล็อก" value={f.blocks?.toLocaleString()} />
        <Stat label="โควตา / ใช้ไป"
              value={q.type === 'limited' ? q.value?.toLocaleString() : q.type}
              sub={quota?.totalUsage != null ? quota.totalUsage.toLocaleString() : null} />
      </div>

      <section className="card">
        <div className="row spread"><h3>รายงานรายได้ (จากสลิปที่ยืนยัน)</h3></div>
        <div className="row wrap" style={{ gap: 6, alignItems: 'center' }}>
          <input type="date" value={rf.frm} onChange={(e) => setRf({ ...rf, frm: e.target.value })} />
          <span className="muted">–</span>
          <input type="date" value={rf.to} onChange={(e) => setRf({ ...rf, to: e.target.value })} />
          <select value={rf.group} onChange={(e) => setRf({ ...rf, group: e.target.value })}>
            <option value="course">ตามหลักสูตร</option><option value="bank">ตามธนาคาร</option>
            <option value="month">ตามเดือน</option><option value="day">ตามวัน</option>
          </select>
          <button className="sm" onClick={loadRev}>ดู</button>
          <button className="sm" onClick={async () => {
            try {
              const csv = await api.get('/reports/revenue?' + new URLSearchParams({ ...rf, format: 'csv' }))
              const text = typeof csv === 'string' ? csv : (csv.detail || JSON.stringify(csv))
              const a = document.createElement('a')
              a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
              a.download = `revenue-${rf.group}.csv`; a.click()
            } catch (e) { t.err(e.message) }
          }}>⬇ CSV</button>
        </div>
        {rev && (
          <>
            <div className="stat" style={{ margin: '8px 0' }}>
              <div><b>฿{rev.total?.toLocaleString()}</b><span className="muted"> รวม</span></div>
              <div><b>{rev.count}</b><span className="muted"> รายการ</span></div>
            </div>
            <table>
              <thead><tr><th>{rf.group === 'course' ? 'หลักสูตร' : rf.group === 'bank' ? 'ธนาคาร' : 'ช่วงเวลา'}</th><th>จำนวน</th><th>ยอดเงิน</th></tr></thead>
              <tbody>
                {rev.rows.map((r) => (
                  <tr key={r.key}><td>{r.key}</td><td>{r.count}</td><td>฿{r.amount.toLocaleString()}</td></tr>
                ))}
                {!rev.rows.length && <tr><td colSpan={3} className="muted">ไม่มีข้อมูลในช่วงนี้</td></tr>}
              </tbody>
            </table>
          </>
        )}
      </section>

      {funnel && (
        <div className="grid two">
          <section className="card">
            <h3>Funnel</h3>
            {funnel.funnel.map((f, i) => {
              const max = funnel.funnel[0].count || 1
              return (
                <div key={i} className="usage-row" style={{ gridTemplateColumns: '110px 1fr 90px' }}>
                  <span className="usage-name">{f.step}</span>
                  <span className="usage-track"><span className="usage-fill" style={{ width: `${(f.count / max) * 100}%` }} /></span>
                  <span className="usage-count">{f.count.toLocaleString()} <span className="muted">({Math.round(f.count / max * 100)}%)</span></span>
                </div>
              )
            })}
          </section>
          <section className="card">
            <h3>Cohort — ยังติดตามอยู่ (ตามเดือนที่เพิ่มเพื่อน)</h3>
            {funnel.cohorts.length ? (
              <table>
                <thead><tr><th>เดือน</th><th>เพิ่มเพื่อน</th><th>ยังอยู่</th><th>%</th></tr></thead>
                <tbody>
                  {funnel.cohorts.map((c) => (
                    <tr key={c.month}><td>{c.month}</td><td>{c.joined}</td><td>{c.retained}</td>
                      <td><b>{c.rate}%</b></td></tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted sm">ยังไม่มีข้อมูล follow_history พอ (มาจาก webhook)</p>}
          </section>
        </div>
      )}

      {follows?.series?.length > 0 && (
        <section className="card">
          <h3>Follow / Unfollow แบบเรียลไทม์ (จาก webhook, 14 วัน)</h3>
          <div className="stat" style={{ marginBottom: 10 }}>
            <div><b>+{follows.totals.new_follow}</b><span className="muted"> เพิ่มใหม่</span></div>
            <div><b>+{follows.totals.unblock}</b><span className="muted"> unblock</span></div>
            <div><b>-{follows.totals.unfollow}</b><span className="muted"> บล็อก/ลบ</span></div>
            <div><b>{follows.totals.net >= 0 ? '+' : ''}{follows.totals.net}</b><span className="muted"> สุทธิ</span></div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={follows.series}>
              <XAxis dataKey="day" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="follow" name="follow" fill="#06c755" stackId="a" />
              <Bar dataKey="unfollow" name="unfollow" fill="#dc2626" stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </section>
      )}

      {!!history.length && (
        <section className="card">
          <h3>แนวโน้มผู้ติดตาม (LINE insight, 30 วัน)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history}>
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="followers" stroke="#06c755" dot={false} />
              <Line type="monotone" dataKey="blocks" stroke="#dc2626" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </section>
      )}

      {demo.genders?.length > 0 && (
        <div className="grid two">
          <section className="card">
            <h3>เพศ</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={demo.genders}>
                <XAxis dataKey="gender" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} />
                <Tooltip /><Bar dataKey="percentage" fill="#06c755" />
              </BarChart>
            </ResponsiveContainer>
          </section>
          <section className="card">
            <h3>อายุ</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={demo.ages}>
                <XAxis dataKey="age" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 11 }} />
                <Tooltip /><Bar dataKey="percentage" fill="#0ea5e9" />
              </BarChart>
            </ResponsiveContainer>
          </section>
        </div>
      )}

      <section className="card">
        <h3>การส่งข้อความ ({insight.date})</h3>
        <pre className="mono xs">{JSON.stringify(insight.delivery, null, 2)}</pre>
      </section>
    </div>
  )
}
