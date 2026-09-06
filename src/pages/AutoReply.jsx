import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'

const MATCH = { contains: 'มีคำนี้', exact: 'ตรงเป๊ะ', prefix: 'ขึ้นต้นด้วย', any: 'ทุกข้อความ' }
const EMPTY = { name: '', match_type: 'contains', keywords: '', priority: 0, enabled: true, messages: [blank('text')] }

export default function AutoReply() {
  const t = useToast()
  const [rules, setRules] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.autoReplies().then((d) => setRules(d.rules)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const edit = (r) => setForm({
    ...r, keywords: (r.keywords || []).join(', '),
    messages: r.messages?.length ? r.messages : [blank('text')],
  })

  const save = async () => {
    setBusy(true)
    try {
      await api.saveAutoReply({
        id: form.id,
        name: form.name,
        match_type: form.match_type,
        enabled: form.enabled,
        priority: Number(form.priority) || 0,
        keywords: form.keywords.split(',').map((s) => s.trim()).filter(Boolean),
        messages: form.messages,
      })
      t.ok('บันทึกแล้ว'); setForm(null); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const toggle = async (r) => {
    try { await api.saveAutoReply({ ...r, keywords: r.keywords, enabled: !r.enabled }); load() }
    catch (e) { t.err(e.message) }
  }

  if (!rules) return <Spinner />

  return (
    <div>
      <h1>ตอบกลับอัตโนมัติ</h1>

      <section className="card">
        <div className="row spread">
          <h3>กฎ ({rules.length})</h3>
          <button className="sm primary" onClick={() => setForm({ ...EMPTY })}>+ เพิ่มกฎ</button>
        </div>
        <table>
          <thead><tr><th>เปิด</th><th>ชื่อ</th><th>เงื่อนไข</th><th>คำ</th><th>ครั้งที่ตอบ</th><th></th></tr></thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <td><input type="checkbox" checked={r.enabled} onChange={() => toggle(r)} /></td>
                <td>{r.name || <span className="muted">(ไม่มีชื่อ)</span>}</td>
                <td>{MATCH[r.match_type]}</td>
                <td className="sm">{(r.keywords || []).join(', ') || (r.match_type === 'any' ? '—' : '')}</td>
                <td>{r.hits || 0}</td>
                <td className="row">
                  <button className="xs" onClick={() => edit(r)}>แก้ไข</button>
                  <button className="xs danger" onClick={() => confirm('ลบกฎนี้?') && api.delAutoReply(r.id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                </td>
              </tr>
            ))}
            {!rules.length && <tr><td colSpan={6} className="muted center">ยังไม่มีกฎ</td></tr>}
          </tbody>
        </table>
        <p className="muted xs">ทำงานเมื่อ webhook ตั้งค่าไว้แล้ว — user พิมพ์ข้อความเข้ามา ระบบจะตอบด้วย reply token ทันที (ฟรี ไม่กินโควตา)</p>
      </section>

      {form && (
        <div className="modal-bg" onClick={() => setForm(null)}>
          <div className="modal" style={{ maxWidth: 620 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread">
              <h3>{form.id ? 'แก้ไขกฎ' : 'กฎใหม่'}</h3>
              <button className="xs" onClick={() => setForm(null)}>✕</button>
            </div>
            <input placeholder="ชื่อกฎ" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <div className="row wrap">
              <select value={form.match_type} onChange={(e) => setForm({ ...form, match_type: e.target.value })}>
                {Object.entries(MATCH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <input placeholder="priority" type="number" style={{ width: 90 }}
                     value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} />
              <label><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> เปิดใช้</label>
            </div>
            {form.match_type !== 'any' && (
              <input placeholder="คำ/วลี คั่นด้วย , (เช่น สวัสดี, hello, hi)"
                     value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
            )}
            <div className="row spread" style={{ marginTop: 8 }}>
              <b className="sm">ข้อความตอบ ({form.messages.length}/5)</b>
              <button className="xs" disabled={form.messages.length >= 5}
                      onClick={() => setForm({ ...form, messages: [...form.messages, blank('text')] })}>+ ข้อความ</button>
            </div>
            {form.messages.map((m, i) => (
              <MessageEditor key={i} index={i} msg={m}
                             onChange={(nm) => setForm({ ...form, messages: form.messages.map((x, j) => j === i ? nm : x) })}
                             onRemove={() => setForm({ ...form, messages: form.messages.filter((_, j) => j !== i) })} />
            ))}
            <div className="phone" style={{ margin: '10px 0' }}>
              <div className="phone-body">
                {form.messages.map((m, i) => <MessagePreview key={i} msg={m} />)}
              </div>
            </div>
            <button className="primary" onClick={save} disabled={busy}>บันทึกกฎ</button>
          </div>
        </div>
      )}
    </div>
  )
}
