import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, useToast } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'
import TemplateGallery from '../components/TemplateGallery.jsx'

const EMPTY = { data: '', label: '', match: 'exact', enabled: true, messages: [blank('text')] }

export default function Postbacks() {
  const t = useToast()
  const [list, setList] = useState(null)
  const [form, setForm] = useState(null)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [gallery, setGallery] = useState(false)
  const [importText, setImportText] = useState('')

  const load = () => api.postbacks().then((d) => setList(d.actions)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    if (!form.data.trim()) return t.err('ใส่ postback data ก่อน')
    setBusy(true)
    try { await api.savePostback(form); t.ok('บันทึกแล้ว'); setForm(null); load() }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const doImport = async () => {
    const codes = importText.split(/[\s,\n]+/).map((s) => s.trim()).filter(Boolean)
    if (!codes.length) return
    setBusy(true)
    try {
      const r = await api.importPostbacks(codes)
      t.ok(`สร้าง ${r.created} ใหม่ / มีอยู่แล้ว ${r.existing} (ทั้งหมด ${r.total}) — ตั้งข้อความแล้วเปิดใช้`)
      setImportText(''); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  if (!list) return <Spinner />
  const filtered = q ? list.filter((x) => (x.data + (x.label || '')).toLowerCase().includes(q.toLowerCase())) : list
  const onCount = list.filter((x) => x.enabled).length

  return (
    <div>
      <h1>จัดการ Postback <span className="muted sm">({onCount}/{list.length} เปิดใช้)</span></h1>

      <section className="card">
        <h3>นำเข้า postback code เป็นชุด</h3>
        <textarea rows={3} placeholder="วาง code คั่นด้วยขึ้นบรรทัด/comma เช่น&#10;FC70_REGISTER, PC70_REGISTER, pass&course=PC, fc=received"
                  value={importText} onChange={(e) => setImportText(e.target.value)} />
        <button className="sm" onClick={doImport} disabled={busy}>{busy && <InlineSpinner />}สร้าง stub (ปิดไว้)</button>
      </section>

      <section className="card">
        <div className="row spread wrap">
          <input placeholder="ค้นหา code / ชื่อ" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="sm primary" onClick={() => setForm({ ...EMPTY })}>+ เพิ่ม</button>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>เปิด</th><th>postback data</th><th>ชื่อ</th><th>match</th><th>ตอบด้วย</th><th>ครั้ง</th><th></th></tr></thead>
            <tbody>
              {filtered.map((a) => (
                <tr key={a.id}>
                  <td><input type="checkbox" checked={a.enabled}
                             onChange={() => api.savePostback({ ...a, enabled: !a.enabled }).then(load)} /></td>
                  <td className="mono xs">{a.data}</td>
                  <td>{a.label || <span className="muted">—</span>}</td>
                  <td className="xs">{a.match}</td>
                  <td className="muted xs">{(a.messages || []).map((m) => m.type).join(', ') || '(ว่าง)'}</td>
                  <td>{a.hits || 0}</td>
                  <td className="row">
                    <button className="xs" onClick={() => setForm({ ...a, messages: a.messages?.length ? a.messages : [blank('text')] })}>แก้ไข</button>
                    <button className="xs danger" onClick={() => confirm('ลบ?') && api.delPostback(a.id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                  </td>
                </tr>
              ))}
              {!filtered.length && <tr><td colSpan={7} className="muted center">ยังไม่มี — นำเข้า code จากบอทเดิม หรือกด "+ เพิ่ม"</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="muted xs">postback มาก่อน "ตอบอัตโนมัติ" — ถ้า match ที่นี่แล้วจะไม่ไปเช็คกฎ keyword · match "prefix" = ขึ้นต้นด้วย (เช่น <code>action=register&</code>)</p>
      </section>

      {form && (
        <div className="modal-bg" onClick={() => setForm(null)}>
          <div className="modal" style={{ maxWidth: 620 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>{form.id ? 'แก้ไข Postback' : 'Postback ใหม่'}</h3><button className="xs" onClick={() => setForm(null)}>✕</button></div>
            <label className="sm">postback data (จากปุ่ม/rich menu)</label>
            <input className="mono" value={form.data} onChange={(e) => setForm({ ...form, data: e.target.value })} placeholder="FC70_REGISTER" />
            <div className="row wrap">
              <input placeholder="ชื่อ (สำหรับจำ)" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
              <select value={form.match} onChange={(e) => setForm({ ...form, match: e.target.value })}>
                <option value="exact">ตรงเป๊ะ</option>
                <option value="prefix">ขึ้นต้นด้วย</option>
              </select>
              <label><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> เปิดใช้</label>
            </div>
            <div className="row spread" style={{ marginTop: 8 }}>
              <b className="sm">ข้อความตอบ ({form.messages.length}/5)</b>
              <div className="row">
                <button className="xs primary" onClick={() => setGallery(true)}>📚</button>
                <button className="xs" disabled={form.messages.length >= 5}
                        onClick={() => setForm({ ...form, messages: [...form.messages, blank('text')] })}>+ ข้อความ</button>
              </div>
            </div>
            {form.messages.map((m, i) => (
              <MessageEditor key={i} index={i} msg={m}
                             onChange={(nm) => setForm({ ...form, messages: form.messages.map((x, j) => j === i ? nm : x) })}
                             onRemove={() => setForm({ ...form, messages: form.messages.filter((_, j) => j !== i) })} />
            ))}
            <div className="phone"><div className="phone-body">
              {form.messages.map((m, i) => <MessagePreview key={i} msg={m} />)}
            </div></div>
            <button className="primary" onClick={save} disabled={busy}>{busy && <InlineSpinner />}บันทึก</button>
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
