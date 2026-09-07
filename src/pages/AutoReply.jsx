import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'
import TemplateGallery from '../components/TemplateGallery.jsx'

const TRIGGERS = [
  { v: 'text', label: 'ผู้ใช้พิมพ์ข้อความ (ระบุคำ)', kw: true },
  { v: 'fallback', label: 'พิมพ์ข้อความ แต่ไม่ตรงคำใดเลย (fallback)' },
  { v: 'follow', label: 'เพิ่มเพื่อน / ปลดบล็อก (ต้อนรับ)' },
  { v: 'postback', label: 'กดปุ่ม / Rich Menu (postback)', kw: true, kwLabel: 'ค่า postback data' },
  { v: 'sticker', label: 'ส่งสติกเกอร์' },
  { v: 'image', label: 'ส่งรูปภาพ' },
  { v: 'video', label: 'ส่งวิดีโอ' },
  { v: 'audio', label: 'ส่งเสียง' },
  { v: 'file', label: 'ส่งไฟล์' },
  { v: 'location', label: 'ส่งตำแหน่ง / พิกัด' },
  { v: 'beacon', label: 'เข้าใกล้ LINE Beacon' },
]
const MATCH = { contains: 'มีคำนี้', exact: 'ตรงเป๊ะ', prefix: 'ขึ้นต้นด้วย', any: 'พิมพ์อะไรก็ตอบ' }
const EMPTY = { trigger: 'text', name: '', match_type: 'contains', keywords: '', priority: 0, enabled: true, messages: [blank('text')] }

export default function AutoReply() {
  const t = useToast()
  const [rules, setRules] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [gallery, setGallery] = useState(false)

  const load = () => api.autoReplies().then((d) => setRules(d.rules)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const trg = (v) => TRIGGERS.find((x) => x.v === v) || TRIGGERS[0]

  const edit = (r) => setForm({
    ...EMPTY, ...r, keywords: (r.keywords || []).join(', '),
    messages: r.messages?.length ? r.messages : [blank('text')],
  })

  const save = async () => {
    setBusy(true)
    try {
      await api.saveAutoReply({
        id: form.id, name: form.name, trigger: form.trigger,
        match_type: form.match_type, enabled: form.enabled,
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
  const cur = form && trg(form.trigger)

  return (
    <div>
      <h1>ตอบอัตโนมัติ</h1>

      <section className="card">
        <div className="row spread">
          <h3>กฎ ({rules.length})</h3>
          <button className="sm primary" onClick={() => setForm({ ...EMPTY })}>+ เพิ่มกฎ</button>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>เปิด</th><th>ชื่อ</th><th>ทำงานเมื่อ</th><th>คำ/data</th><th>ตอบด้วย</th><th>ตอบไป</th><th></th></tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td><input type="checkbox" checked={r.enabled} onChange={() => toggle(r)} /></td>
                  <td>{r.name || <span className="muted">(ไม่มีชื่อ)</span>}</td>
                  <td className="sm">{trg(r.trigger).label}{trg(r.trigger).kw && ` · ${MATCH[r.match_type]}`}</td>
                  <td className="sm">{(r.keywords || []).join(', ') || '—'}</td>
                  <td className="muted xs">{(r.messages || []).map((m) => m.type).join(', ')}</td>
                  <td>{r.hits || 0}</td>
                  <td className="row">
                    <button className="xs" onClick={() => edit(r)}>แก้ไข</button>
                    <button className="xs danger" onClick={() => confirm('ลบกฎนี้?') && api.delAutoReply(r.id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                  </td>
                </tr>
              ))}
              {!rules.length && <tr><td colSpan={7} className="muted center">ยังไม่มีกฎ</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="muted xs">ทำงานเมื่อตั้ง Webhook URL ใน LINE แล้ว — ตอบด้วย reply token (ฟรี ไม่กินโควตา) · กฎเรียงตาม priority มาก→น้อย เอากฎแรกที่ตรง</p>
      </section>

      {form && (
        <div className="modal-bg" onClick={() => setForm(null)}>
          <div className="modal" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread">
              <h3>{form.id ? 'แก้ไขกฎ' : 'กฎใหม่'}</h3>
              <button className="xs" onClick={() => setForm(null)}>✕</button>
            </div>

            <label className="sm">ชื่อกฎ</label>
            <input placeholder="เช่น ต้อนรับ, ตอบเมื่อส่งรูป" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />

            <label className="sm">ทำงานเมื่อ (event)</label>
            <select value={form.trigger} onChange={(e) => setForm({ ...form, trigger: e.target.value })}>
              {TRIGGERS.map((x) => <option key={x.v} value={x.v}>{x.label}</option>)}
            </select>

            {cur.kw && (
              <>
                <div className="row wrap" style={{ marginTop: 6 }}>
                  <select value={form.match_type} onChange={(e) => setForm({ ...form, match_type: e.target.value })}>
                    {Object.entries(MATCH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <span className="sm muted">{cur.kwLabel || 'คำ/วลี'}</span>
                </div>
                {form.match_type !== 'any' && (
                  <input placeholder={`${cur.kwLabel || 'คำ/วลี'} คั่นด้วย , เช่น สวัสดี, hello`}
                         value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
                )}
              </>
            )}

            <div className="row wrap" style={{ marginTop: 6 }}>
              <label><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> เปิดใช้</label>
              <label>priority <input type="number" style={{ width: 70 }} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></label>
            </div>
            <p className="muted xs">💡 ใส่ <code>{'{name}'}</code> ในข้อความ = แทนที่ด้วยชื่อ LINE ของผู้ใช้อัตโนมัติ</p>

            <div className="row spread" style={{ marginTop: 8 }}>
              <b className="sm">ข้อความตอบ ({form.messages.length}/5)</b>
              <div className="row">
                <button className="xs primary" onClick={() => setGallery(true)}>📚 คลังเทมเพลต</button>
                <button className="xs" disabled={form.messages.length >= 5}
                        onClick={() => setForm({ ...form, messages: [...form.messages, blank('text')] })}>+ ข้อความ</button>
              </div>
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

      {gallery && (
        <TemplateGallery onClose={() => setGallery(false)}
          onPick={(msgs) => setForm((f) => ({ ...f, messages: msgs.slice(0, 5) }))} />
      )}
    </div>
  )
}
