import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'

export default function Messaging() {
  const t = useToast()
  const [messages, setMessages] = useState([blank('text')])
  const [mode, setMode] = useState('broadcast') // broadcast | push | db
  const [to, setTo] = useState('')
  const [tag, setTag] = useState('')
  const [menu, setMenu] = useState('')
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState([])
  const [usage, setUsage] = useState([]) // [{richMenuId, name, count}] เรียงมาก→น้อย
  const [schedAt, setSchedAt] = useState('')
  const [scheduled, setScheduled] = useState([])

  const loadHistory = () => api.broadcastHistory().then((d) => setHistory(d.broadcasts)).catch(() => {})
  const loadScheduled = () => api.scheduled().then((d) => setScheduled(d.jobs)).catch(() => {})
  useEffect(() => {
    loadHistory(); loadScheduled()
    api.richmenuUsage().then((d) => setUsage(d.items)).catch(() => {})
  }, [])

  const doSchedule = async () => {
    if (!schedAt) return t.err('เลือกเวลาก่อน')
    setBusy(true)
    try {
      await api.schedule({ kind: 'broadcast', runAt: new Date(schedAt).toISOString(), messages })
      t.ok('ตั้งเวลาส่ง broadcast แล้ว'); setSchedAt(''); loadScheduled()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const menus = usage.filter((u) => u.richMenuId)
  const selectedCount = menu
    ? usage.find((u) => u.richMenuId === menu)?.count ?? 0
    : usage.reduce((s, u) => s + (u.richMenuId ? u.count : 0), 0)

  const setMsg = (i, m) => setMessages((arr) => arr.map((x, j) => (j === i ? m : x)))
  const addMsg = () => messages.length < 5 && setMessages((a) => [...a, blank('text')])
  const rmMsg = (i) => setMessages((a) => a.filter((_, j) => j !== i))

  const targetLabel = {
    broadcast: 'ทุกคนที่ติดตาม',
    push: `${to.split(/[\s,]+/).filter(Boolean).length} userId`,
    db: `${menu ? menus.find((m) => m.richMenuId === menu)?.name : 'ทุกเมนู'}${tag ? ` +tag:${tag}` : ''} · ~${selectedCount.toLocaleString()} คน`,
  }[mode]

  const doValidate = async () => {
    try { await api.validateMsg(messages); t.ok('รูปแบบข้อความถูกต้อง ✓') }
    catch (e) { t.err(e.message) }
  }

  const sendTest = async () => {
    setBusy(true)
    try { await api.post('/message/test', { messages }); t.ok('ส่งเข้า LINE ตัวเองแล้ว — เช็คในแอป LINE') }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const send = async () => {
    if (!confirm(`ส่ง ${messages.length} ข้อความ หา ${targetLabel}?`)) return
    setBusy(true)
    try {
      let r
      if (mode === 'broadcast') r = await api.broadcast({ messages })
      else if (mode === 'push') r = await api.push({ to: to.split(/[\s,]+/).filter(Boolean), messages })
      else r = await api.multicastDb({ tag, menu, messages })
      t.ok('ส่งแล้ว ' + (r.sent != null ? `(${r.sent} คน)` : r.requestId ? `req ${r.requestId.slice(0, 8)}` : ''))
      loadHistory()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <h1>ส่งข้อความ</h1>

      <div className="msg-layout">
        {/* ---------- ซ้าย: ตัวแก้ไข ---------- */}
        <div>
          <section className="card">
            <h3>ปลายทาง</h3>
            <div className="row wrap">
              {['broadcast', 'push', 'db'].map((m) => (
                <label key={m}>
                  <input type="radio" checked={mode === m} onChange={() => setMode(m)} />{' '}
                  {{ broadcast: 'Broadcast (ทุกคน)', push: 'Push (ระบุ userId)', db: 'ตาม filter ใน DB' }[m]}
                </label>
              ))}
            </div>
            {mode === 'push' && (
              <textarea rows={3} placeholder="userId คั่นด้วยขึ้นบรรทัด/comma (≤500 = multicast, 1 = push)"
                        value={to} onChange={(e) => setTo(e.target.value)} />
            )}
            {mode === 'db' && (
              <>
                <div className="row wrap">
                  <input placeholder="tag" value={tag} onChange={(e) => setTag(e.target.value)} />
                  <select value={menu} onChange={(e) => setMenu(e.target.value)}>
                    <option value="">— ทุก rich menu ({menus.reduce((s, m) => s + m.count, 0).toLocaleString()} คน) —</option>
                    {menus.map((m) => (
                      <option key={m.richMenuId} value={m.richMenuId}>
                        {m.name} — {m.count.toLocaleString()} คน{m.isDefault ? ' (default)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="usage-bars">
                  {usage.map((u) => {
                    const max = usage[0]?.count || 1
                    return (
                      <div key={u.richMenuId || 'none'} className="usage-row"
                           onClick={() => u.richMenuId && setMenu(u.richMenuId === menu ? '' : u.richMenuId)}
                           style={{ cursor: u.richMenuId ? 'pointer' : 'default' }}>
                        <span className="usage-name">{u.name}</span>
                        <span className="usage-track"><span className="usage-fill" style={{ width: `${(u.count / max) * 100}%` }} /></span>
                        <span className="usage-count">{u.count.toLocaleString()}</span>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </section>

          <section className="card">
            <div className="row spread">
              <h3>ข้อความ ({messages.length}/5)</h3>
              <button className="sm" onClick={addMsg} disabled={messages.length >= 5}>+ เพิ่มข้อความ</button>
            </div>
            {messages.map((m, i) => (
              <MessageEditor key={i} index={i} msg={m}
                             onChange={(nm) => setMsg(i, nm)}
                             onRemove={() => rmMsg(i)} />
            ))}
          </section>

          <div className="row">
            <button className="sm" onClick={doValidate} disabled={busy}>ตรวจรูปแบบ</button>
            <button className="sm" onClick={sendTest} disabled={busy}>ส่งหาตัวเอง (ทดสอบ)</button>
            <button className="primary" onClick={send} disabled={busy}>ส่งจริง → {targetLabel}</button>
          </div>

          <section className="card" style={{ marginTop: 16 }}>
            <h3>ตั้งเวลาส่ง (Broadcast)</h3>
            <div className="row wrap">
              <input type="datetime-local" value={schedAt} onChange={(e) => setSchedAt(e.target.value)} />
              <button className="sm" onClick={doSchedule} disabled={busy}>ตั้งเวลา</button>
            </div>
            {scheduled.filter((j) => j.status === 'pending').length > 0 && (
              <table style={{ marginTop: 10 }}>
                <thead><tr><th>เวลา</th><th>ชนิด</th><th></th></tr></thead>
                <tbody>
                  {scheduled.filter((j) => j.status === 'pending').map((j) => (
                    <tr key={j.id}>
                      <td className="sm">{new Date(j.run_at).toLocaleString('th-TH')}</td>
                      <td>{j.kind}</td>
                      <td><button className="xs danger" onClick={() => api.cancelScheduled(j.id).then(loadScheduled)}>ยกเลิก</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="muted xs">ระบบเช็คทุก 5 นาที — เวลาส่งจริงอาจคลาดเคลื่อน ≤ 5 นาที</p>
          </section>
        </div>

        {/* ---------- ขวา: พรีวิว ---------- */}
        <div className="preview-pane">
          <div className="phone">
            <div className="phone-head">พรีวิว</div>
            <div className="phone-body">
              {messages.map((m, i) => (
                <div key={i} className="ln-row"><MessagePreview msg={m} /></div>
              ))}
            </div>
          </div>
          <p className="muted xs">* พรีวิวเป็นการประมาณ — สติกเกอร์/รูป/Flex บางส่วนอาจต่างจากใน LINE จริงเล็กน้อย</p>
        </div>
      </div>

      <section className="card">
        <h3>ประวัติการส่ง</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>ชนิด</th><th>ปลายทาง</th><th>ข้อความ</th><th>สถานะ</th><th>เวลา</th></tr></thead>
            <tbody>
              {history.map((b) => (
                <tr key={b.id}>
                  <td>{b.kind}</td>
                  <td>{b.target_count?.toLocaleString()}</td>
                  <td className="muted xs">{(b.messages || []).map((m) => m.type).join(', ')}</td>
                  <td><span className={`chip ${b.status}`}>{b.status}</span></td>
                  <td className="muted sm">{new Date(b.created_at).toLocaleString('th-TH')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
