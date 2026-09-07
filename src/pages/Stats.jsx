import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { api } from '../lib/api.js'
import { Spinner, Stat, useToast } from '../lib/ui.jsx'

export default function Stats() {
  const t = useToast()
  const [insight, setInsight] = useState(null)
  const [history, setHistory] = useState([])
  const [quota, setQuota] = useState(null)
  const [follows, setFollows] = useState(null)

  useEffect(() => {
    api.quota().then(setQuota).catch(() => {})
    api.insight().then(setInsight).catch((e) => t.err(e.message))
    api.statsHistory(30).then((d) => setHistory([...d.days].reverse())).catch(() => {})
    api.followStats(14).then(setFollows).catch(() => {})
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
