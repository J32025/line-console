import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { SkeletonRows, InlineSpinner, useToast } from '../lib/ui.jsx'

export default function Events() {
  const t = useToast()
  const [tab, setTab] = useState('events')
  const [events, setEvents] = useState(null)
  const [ops, setOps] = useState(null)
  const [type, setType] = useState('')
  const [replyTo, setReplyTo] = useState(null) // event
  const [replyText, setReplyText] = useState('')
  const [busy, setBusy] = useState(false)

  const loadEvents = () => api.events({ type, limit: 200 }).then((d) => setEvents(d.events)).catch((e) => t.err(e.message))
  useEffect(() => { loadEvents() }, [type]) // eslint-disable-line
  useEffect(() => { api.operations().then((d) => setOps(d.operations)).catch(() => {}) }, [])

  const sendReply = async () => {
    if (!replyText.trim()) return
    setBusy(true)
    try {
      const r = await api.post(`/events/${replyTo.id}/reply`, { messages: [replyText] })
      t.ok(r.note || (r.via === 'push' ? 'ส่งแบบ push' : 'ตอบกลับแล้ว'))
      setReplyTo(null); setReplyText(''); loadEvents()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const tokenAge = (e) => Math.round((Date.now() - new Date(e.created_at)) / 1000)

  return (
    <div>
      <h1>Events & Logs</h1>
      <div className="row">
        <button className={tab === 'events' ? 'primary sm' : 'sm'} onClick={() => setTab('events')}>Webhook events</button>
        <button className={tab === 'ops' ? 'primary sm' : 'sm'} onClick={() => setTab('ops')}>Operations</button>
        <button className="sm" onClick={loadEvents}>รีเฟรช</button>
      </div>

      {tab === 'events' && (
        <section className="card">
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">ทุกชนิด</option>
            {['follow', 'unfollow', 'message', 'postback', 'join', 'leave', 'memberJoined'].map((x) => <option key={x}>{x}</option>)}
          </select>
          {!events ? <SkeletonRows rows={8} cols={5} /> : (
            <div className="table-scroll">
              <table>
                <thead><tr><th>ชนิด</th><th>ผู้ใช้</th><th>ข้อความ / postback</th><th>reply token</th><th>เวลา</th><th></th></tr></thead>
                <tbody>
                  {events.map((e) => {
                    const age = tokenAge(e)
                    const canReply = e.reply_token && age < 55
                    return (
                      <tr key={e.id}>
                        <td><span className={`chip ${e.event_type}`}>{e.event_type}</span></td>
                        <td className="mono xs">{e.line_user_id?.slice(0, 12) || '–'}</td>
                        <td>
                          {e.text || <span className="muted">{e.message_type || ''}</span>}
                          {e.postback_data && <span className="chip">pb: {e.postback_data}</span>}
                          {e.auto_replied && <span className="chip ok">ตอบแล้ว</span>}
                        </td>
                        <td className="xs">
                          {e.reply_token
                            ? <span className={canReply ? 'chip ok' : 'chip'}>{canReply ? `ใช้ได้ (${55 - age}s)` : 'หมดอายุ'}</span>
                            : <span className="muted">–</span>}
                        </td>
                        <td className="muted xs">{new Date(e.created_at).toLocaleTimeString('th-TH')}</td>
                        <td>
                          {e.line_user_id && (
                            <button className="xs" onClick={() => { setReplyTo(e); setReplyText('') }}>ตอบ</button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                  {!events.length && <tr><td colSpan={6} className="muted center">ยังไม่มี event — ตั้ง Webhook URL ใน LINE Developers ก่อน: <code>/api/webhook</code></td></tr>}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted xs">reply token ของ LINE ใช้ได้ครั้งเดียว ภายใน ~1 นาที — ถ้าหมดอายุระบบจะส่งแบบ push แทน (กินโควตา)</p>
        </section>
      )}

      {tab === 'ops' && (
        <section className="card">
          {!ops ? <SkeletonRows rows={6} cols={5} /> : (
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

      {replyTo && (
        <div className="modal-bg" onClick={() => setReplyTo(null)}>
          <div className="modal" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>ตอบกลับ</h3><button className="xs" onClick={() => setReplyTo(null)}>✕</button></div>
            <p className="muted xs mono">{replyTo.line_user_id}</p>
            {replyTo.text && <p className="sm" style={{ background: '#f4f4f4', padding: 8, borderRadius: 6 }}>{replyTo.text}</p>}
            <textarea rows={3} placeholder="พิมพ์คำตอบ…" value={replyText} onChange={(e) => setReplyText(e.target.value)} />
            <button className="primary" onClick={sendReply} disabled={busy}>{busy && <InlineSpinner />}ส่ง</button>
          </div>
        </div>
      )}
    </div>
  )
}
