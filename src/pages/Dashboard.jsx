import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, Stat } from '../lib/ui.jsx'

export default function Dashboard() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.dashboard().then(setD).catch((e) => setErr(e.message))
  }, [])

  if (err) return <p className="err">{err}</p>
  if (!d) return <Spinner />

  const q = d.quota?.quota || {}
  return (
    <div>
      <h1>แดชบอร์ด</h1>
      <div className="grid stats">
        <Stat label="ผู้ใช้ทั้งหมด" value={d.users.total} />
        <Stat label="กำลังติดตาม" value={d.users.following} />
        <Stat label="ไม่มี Rich Menu" value={d.users.no_menu} />
        <Stat label="โควตาข้อความ" value={q.type === 'limited' ? q.value?.toLocaleString() : q.type || '–'}
              sub={d.quota?.totalUsage != null ? `ใช้ไป ${d.quota.totalUsage.toLocaleString()}` : null} />
      </div>

      <div className="grid two">
        <section className="card">
          <h3>บอท</h3>
          {d.bot?.displayName ? (
            <div className="row">
              {d.bot.pictureUrl && <img className="avatar" src={d.bot.pictureUrl} alt="" />}
              <div>
                <div><b>{d.bot.displayName}</b></div>
                <div className="muted sm">{d.bot.basicId} · {d.bot.premiumId || 'unverified'}</div>
                <div className="muted xs">chatMode: {d.bot.chatMode} · webhook: {d.bot.markAsReadMode}</div>
              </div>
            </div>
          ) : <p className="muted">{d.bot?.error || '–'}</p>}
        </section>

        <section className="card">
          <h3>ปฏิบัติการล่าสุด</h3>
          <ul className="loglist">
            {d.recent_operations.map((o) => (
              <li key={o.id}>
                <span className={`dot ${o.status}`} />
                {o.action}
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
                <td>{b.kind}</td><td>{b.target_count?.toLocaleString()}</td>
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
