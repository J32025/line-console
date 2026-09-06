import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'

export default function Events() {
  const t = useToast()
  const [tab, setTab] = useState('events')
  const [events, setEvents] = useState(null)
  const [ops, setOps] = useState(null)
  const [type, setType] = useState('')

  const loadEvents = () => api.events({ type, limit: 200 }).then((d) => setEvents(d.events)).catch((e) => t.err(e.message))
  useEffect(() => { loadEvents() }, [type]) // eslint-disable-line
  useEffect(() => { api.operations().then((d) => setOps(d.operations)).catch(() => {}) }, [])

  return (
    <div>
      <h1>Events & Logs</h1>
      <div className="row">
        <button className={tab === 'events' ? 'primary sm' : 'sm'} onClick={() => setTab('events')}>Webhook events</button>
        <button className={tab === 'ops' ? 'primary sm' : 'sm'} onClick={() => setTab('ops')}>Operations</button>
      </div>

      {tab === 'events' && (
        <section className="card">
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">ทุกชนิด</option>
            {['follow', 'unfollow', 'message', 'postback', 'join', 'leave'].map((x) => <option key={x}>{x}</option>)}
          </select>
          {!events ? <Spinner /> : (
            <div className="table-scroll">
              <table>
                <thead><tr><th>ชนิด</th><th>userId</th><th>ข้อความ</th><th>เวลา</th></tr></thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id}>
                      <td><span className={`chip ${e.event_type}`}>{e.event_type}</span></td>
                      <td className="mono xs">{e.line_user_id || '–'}</td>
                      <td>{e.text || <span className="muted">{e.message_type || ''}</span>}</td>
                      <td className="muted xs">{new Date(e.created_at).toLocaleString('th-TH')}</td>
                    </tr>
                  ))}
                  {!events.length && <tr><td colSpan={4} className="muted center">ยังไม่มี event (ตั้ง webhook URL ใน LINE ก่อน)</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === 'ops' && (
        <section className="card">
          {!ops ? <Spinner /> : (
            <table>
              <thead><tr><th>action</th><th>actor</th><th>สถานะ</th><th>ผล</th><th>เวลา</th></tr></thead>
              <tbody>
                {ops.map((o) => (
                  <tr key={o.id}>
                    <td>{o.action}</td>
                    <td className="mono xs">{o.actor?.slice(0, 10)}</td>
                    <td><span className={`chip ${o.status}`}>{o.status}</span></td>
                    <td className="muted xs">{JSON.stringify(o.result)?.slice(0, 80)}</td>
                    <td className="muted xs">{new Date(o.created_at).toLocaleString('th-TH')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  )
}
