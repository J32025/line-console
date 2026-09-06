import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../lib/ui.jsx'

const SAMPLE = `[
  { "type": "text", "text": "สวัสดีครับ 👋" }
]`

export default function Messaging() {
  const t = useToast()
  const [mode, setMode] = useState('broadcast')
  const [raw, setRaw] = useState('สวัสดีครับ')
  const [json, setJson] = useState(false)
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

  const messages = () => {
    if (json) return JSON.parse(raw)
    return raw.split('\n---\n').map((x) => x.trim()).filter(Boolean)
  }

  const validate = async () => {
    try { await api.validateMsg(messages()); t.ok('รูปแบบข้อความถูกต้อง') }
    catch (e) { t.err(e.message) }
  }

  const send = async () => {
    let msgs
    try { msgs = messages() } catch { return t.err('JSON ไม่ถูกต้อง') }
    const desc = { broadcast: 'ทุกคนที่ติดตาม', push: `${to.split(/[\s,]+/).filter(Boolean).length} คน`, db: `filter tag/menu` }[mode]
    if (!confirm(`ส่งข้อความหา ${desc}?`)) return
    setBusy(true)
    try {
      let r
      if (mode === 'broadcast') r = await api.broadcast({ messages: msgs })
      else if (mode === 'push') r = await api.push({ to: to.split(/[\s,]+/).filter(Boolean), messages: msgs })
      else r = await api.multicastDb({ tag, menu, messages: msgs })
      t.ok('ส่งแล้ว ' + (r.requestId ? `(req ${r.requestId.slice(0, 8)})` : `${r.sent ?? ''}`))
      loadHistory()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <h1>ส่งข้อความ</h1>
      <section className="card">
        <div className="row wrap">
          {['broadcast', 'push', 'db'].map((m) => (
            <label key={m}>
              <input type="radio" checked={mode === m} onChange={() => setMode(m)} />{' '}
              {{ broadcast: 'Broadcast (ทุกคน)', push: 'Push (ระบุ userId)', db: 'ตาม filter ใน DB' }[m]}
            </label>
          ))}
        </div>

        {mode === 'push' && (
          <textarea rows={3} placeholder="userId คั่นด้วยขึ้นบรรทัด/comma (≤500 = multicast)"
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

        <label className="row"><input type="checkbox" checked={json} onChange={(e) => setJson(e.target.checked)} /> โหมด JSON (array of message objects)</label>
        <textarea rows={json ? 10 : 5} value={raw} onChange={(e) => setRaw(e.target.value)}
                  placeholder={json ? SAMPLE : 'ข้อความ (คั่นหลายข้อความด้วยบรรทัด ---)'} />

        <div className="row">
          <button className="sm" onClick={validate}>ตรวจรูปแบบ</button>
          <button className="primary" disabled={busy} onClick={send}>ส่ง</button>
        </div>
      </section>

      <section className="card">
        <h3>ประวัติการส่ง</h3>
        <table>
          <thead><tr><th>ชนิด</th><th>ปลายทาง</th><th>สถานะ</th><th>requestId</th><th>เวลา</th></tr></thead>
          <tbody>
            {history.map((b) => (
              <tr key={b.id}>
                <td>{b.kind}</td><td>{b.target_count?.toLocaleString()}</td>
                <td><span className={`chip ${b.status}`}>{b.status}</span></td>
                <td className="mono xs">{b.line_request_id?.slice(0, 12)}</td>
                <td className="muted sm">{new Date(b.created_at).toLocaleString('th-TH')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
