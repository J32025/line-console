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
  const [menus, setMenus] = useState([])

  const loadHistory = () => api.broadcastHistory().then((d) => setHistory(d.broadcasts)).catch(() => {})
  useEffect(() => {
    loadHistory()
    api.richmenus().then((d) => setMenus(d.menus)).catch(() => {})
  }, [])

  const setMsg = (i, m) => setMessages((arr) => arr.map((x, j) => (j === i ? m : x)))
  const addMsg = () => messages.length < 5 && setMessages((a) => [...a, blank('text')])
  const rmMsg = (i) => setMessages((a) => a.filter((_, j) => j !== i))

  const targetLabel = {
    broadcast: 'ทุกคนที่ติดตาม',
    push: `${to.split(/[\s,]+/).filter(Boolean).length} userId`,
    db: `filter: ${tag || 'ทุก tag'} / ${menu ? menus.find((m) => m.richMenuId === menu)?.name : 'ทุกเมนู'}`,
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
              <div className="row wrap">
                <input placeholder="tag" value={tag} onChange={(e) => setTag(e.target.value)} />
                <select value={menu} onChange={(e) => setMenu(e.target.value)}>
                  <option value="">— ทุก rich menu —</option>
                  {menus.map((m) => <option key={m.richMenuId} value={m.richMenuId}>{m.name}</option>)}
                </select>
              </div>
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
