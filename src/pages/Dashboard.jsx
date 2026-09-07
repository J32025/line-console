import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '../lib/api.js'
import { Spinner, SkeletonStats, SkeletonRows, InlineSpinner, Stat, useToast } from '../lib/ui.jsx'

export default function Dashboard() {
  const t = useToast()
  const nav = useNavigate()
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')

  const load = () => api.dashboard().then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  const quick = async (label, fn) => {
    setBusy(label)
    try { const r = await fn(); t.ok(`${label}: ` + JSON.stringify(r).slice(0, 90)); load() }
    catch (e) { t.err(e.message) } finally { setBusy('') }
  }

  if (err) return <p className="err">{err}</p>
  if (!d) return (
    <div>
      <h1>แดชบอร์ด</h1>
      <SkeletonStats />
      <div className="card"><SkeletonRows rows={5} cols={2} /></div>
      <div className="loading-text" style={{ textAlign: 'center' }}><InlineSpinner />กำลังโหลดแดชบอร์ด…</div>
    </div>
  )

  const q = d.quota?.quota || {}
  const trend = (d.trend || []).map((x) => ({ ...x, day: x.day?.slice(5) }))

  return (
    <div>
      <h1>แดชบอร์ด</h1>

      <div className="grid stats">
        <Stat label="ผู้ใช้ในระบบ" value={d.users.total?.toLocaleString()} sub={`ติดตาม ${d.users.following?.toLocaleString()}`} />
        <Stat label="ไม่มี Rich Menu" value={d.users.no_menu?.toLocaleString()} />
        <Stat label="โควตาข้อความ"
              value={q.type === 'limited' ? q.value?.toLocaleString() : q.type || '–'}
              sub={d.quota?.totalUsage != null ? `ใช้ ${d.quota.totalUsage.toLocaleString()}` : null} />
        <Stat label="Event 7 วัน"
              value={Object.values(d.events_7d || {}).reduce((a, b) => a + b, 0).toLocaleString()}
              sub={`follow ${d.events_7d?.follow ?? 0} · unfollow ${d.events_7d?.unfollow ?? 0}`} />
      </div>

      <section className="card">
        <h3>Quick actions</h3>
        <div className="row wrap">
          <button className="sm" disabled={busy} onClick={() => nav('/messaging')}>ส่งข้อความ</button>
          <button className="sm" disabled={busy} onClick={() => quick('sync richmenu', () => api.syncMenu({ target: 'all' }))}>
            {busy === 'sync richmenu' && <InlineSpinner />}Sync Rich Menu ทั้งหมด
          </button>
          <button className="sm" disabled={busy} onClick={() => quick('ดึงโปรไฟล์', () => api.refreshProfiles({ target: 'missing', limit: 400 }))}>
            {busy === 'ดึงโปรไฟล์' && <InlineSpinner />}ดึงโปรไฟล์ที่ค้าง
          </button>
          <button className="sm" disabled={busy} onClick={() => nav('/richmenus')}>จัดการ Rich Menu</button>
          <button className="sm" disabled={busy} onClick={() => nav('/segments')}>กลุ่มเป้าหมาย</button>
        </div>
      </section>

      <section className="card">
        <h3>แนวโน้มผู้ติดตาม</h3>
        {trend.length > 1 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="followers" name="ผู้ติดตาม" stroke="#06c755" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="targeted_reaches" name="เข้าถึงได้" stroke="#0ea5e9" dot={false} />
              <Line type="monotone" dataKey="blocks" name="บล็อก" stroke="#dc2626" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="muted sm">ยังไม่มีข้อมูลพอ — ระบบเก็บ snapshot ทุกวัน 08:05 น. (จะสะสมไปเรื่อย ๆ)</p>
        )}
      </section>

      <div className="grid two">
        <section className="card">
          <h3>บอท</h3>
          {d.bot?.displayName ? (
            <div className="row">
              {d.bot.pictureUrl && <img className="avatar" src={d.bot.pictureUrl} alt="" />}
              <div>
                <div><b>{d.bot.displayName}</b></div>
                <div className="muted sm">{d.bot.basicId} · {d.bot.premiumId || 'unverified'}</div>
              </div>
            </div>
          ) : <p className="muted">{d.bot?.error || '–'}</p>}
        </section>

        <section className="card">
          <h3>ปฏิบัติการล่าสุด</h3>
          <ul className="loglist">
            {d.recent_operations.map((o) => (
              <li key={o.id}>
                <span className={`dot ${o.status}`} />{o.action}
                <span className="muted xs"> · {new Date(o.created_at).toLocaleString('th-TH')}</span>
              </li>
            ))}
            {!d.recent_operations.length && <li className="muted">ยังไม่มี</li>}
          </ul>
        </section>
      </div>

      <section className="card">
        <h3>การส่งข้อความล่าสุด</h3>
        <table>
          <thead><tr><th>ชนิด</th><th>ปลายทาง</th><th>สถานะ</th><th>เวลา</th></tr></thead>
          <tbody>
            {d.recent_broadcasts.map((b) => (
              <tr key={b.id}>
                <td>{b.kind}</td><td>{b.target_count?.toLocaleString() ?? '–'}</td>
                <td><span className={`chip ${b.status}`}>{b.status}</span></td>
                <td className="muted sm">{new Date(b.created_at).toLocaleString('th-TH')}</td>
              </tr>
            ))}
            {!d.recent_broadcasts.length && <tr><td colSpan={4} className="muted">ยังไม่มี</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  )
}
