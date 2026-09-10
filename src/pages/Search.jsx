import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'
import UserDetail from '../components/UserDetail.jsx'

export default function Search() {
  const t = useToast()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [uid, setUid] = useState(null)

  const run = (query) => {
    const s = (query ?? q).trim()
    if (s.length < 2) return
    setParams({ q: s }); setBusy(true)
    api.search(s).then(setRes).catch((e) => t.err(e.message)).finally(() => setBusy(false))
  }
  useEffect(() => { if ((params.get('q') || '').length >= 2) run(params.get('q')) }, []) // eslint-disable-line

  return (
    <div>
      <h1>ค้นหา</h1>
      <section className="card">
        <div className="row">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && run()}
                 placeholder="ชื่อ / เบอร์ / อีเมล / สังกัด / userId / ชื่องาน" style={{ flex: 1 }} />
          <button className="sm primary" onClick={() => run()}>ค้นหา</button>
        </div>
      </section>

      {busy ? <Spinner /> : res && (
        <>
          <section className="card">
            <h3>ผู้ใช้ ({res.users.length})</h3>
            {res.users.map((u) => (
              <div key={u.line_user_id} className="row spread" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                <div className="row" style={{ gap: 8 }}>
                  {u.picture_url && <img className="avatar-xs" src={u.picture_url} alt="" />}
                  <div>
                    <b>{u.display_name || <span className="mono xs">{u.line_user_id.slice(0, 14)}</span>}</b>
                    <div className="muted xs">
                      {u.stage && <span className="chip xs">{u.stage}</span>}
                      {(u.tags || []).slice(0, 4).map((tg) => <span key={tg} className="chip xs">{tg}</span>)}
                    </div>
                  </div>
                </div>
                <button className="xs" onClick={() => setUid(u.line_user_id)}>เปิด</button>
              </div>
            ))}
            {!res.users.length && <p className="muted sm">ไม่พบ</p>}
          </section>

          <section className="card">
            <h3>ผู้ลงทะเบียน ({res.registrations.length})</h3>
            <table>
              <tbody>
                {res.registrations.map((r) => (
                  <tr key={r.id}>
                    <td><b>{r.name || r.line_user_id?.slice(0, 10)}</b></td>
                    <td><span className="chip xs">{r.course_raw}</span></td>
                    <td className="sm">{r.tel}</td>
                    <td className="sm muted">{r.org}</td>
                    <td>{r.paid ? '✓ จ่ายแล้ว' : 'ค้าง'}</td>
                    <td><button className="xs" onClick={() => setUid(r.line_user_id)}>เปิด</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!res.registrations.length && <p className="muted sm">ไม่พบ</p>}
          </section>

          {res.tasks?.length > 0 && (
            <section className="card">
              <h3>งาน ({res.tasks.length})</h3>
              <ul className="loglist">
                {res.tasks.map((k) => (
                  <li key={k.id}><span className={`chip xs ${k.status === 'done' ? 'ok' : ''}`}>{k.status}</span> {k.title}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {uid && <UserDetail uid={uid} onClose={() => setUid(null)} onSaved={() => run()} />}
    </div>
  )
}
