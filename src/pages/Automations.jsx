import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, useToast } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'
import TemplateGallery from '../components/TemplateGallery.jsx'

const newStep = () => ({ delayHours: 24, delayMinutes: 0, messages: [blank('text')] })
const EMPTY = { name: '', enabled: true, trigger: 'follow', triggerConfig: {}, steps: [newStep()] }
const TRIGGERS = {
  follow: 'มีคนเพิ่มเพื่อน',
  slip_verified: 'สลิปโอนเงินยืนยันแล้ว',
  tag_added: 'ถูกใส่ tag',
  inactive: 'ไม่ทักแชทมานาน',
}
const trigLabel = (t) => TRIGGERS[t] || t

export default function Automations() {
  const t = useToast()
  const [list, setList] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [gallery, setGallery] = useState(null) // step index

  const load = () => api.automations().then((d) => setList(d.automations)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    if (!form.name.trim()) return t.err('ตั้งชื่อก่อน')
    setBusy(true)
    try {
      await api.saveAutomation(form)
      t.ok('บันทึกแล้ว'); setForm(null); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const setStep = (i, patch) => setForm((f) => ({ ...f, steps: f.steps.map((s, j) => j === i ? { ...s, ...patch } : s) }))

  if (!list) return <Spinner />

  return (
    <div>
      <h1>Automation Flow</h1>

      <section className="card">
        <div className="row spread">
          <h3>โฟลว์ ({list.length})</h3>
          <button className="sm primary" onClick={() => setForm({ ...EMPTY, steps: [newStep()] })}>+ สร้างโฟลว์</button>
        </div>
        <table>
          <thead><tr><th>เปิด</th><th>ชื่อ</th><th>เริ่มเมื่อ</th><th>ขั้นตอน</th><th>รันไป</th><th></th></tr></thead>
          <tbody>
            {list.map((a) => (
              <tr key={a.id}>
                <td><input type="checkbox" checked={a.enabled}
                           onChange={() => api.saveAutomation({ ...a, triggerConfig: a.trigger_config || {}, enabled: !a.enabled }).then(load)} /></td>
                <td>{a.name}</td>
                <td className="sm">
                  {trigLabel(a.trigger)}
                  {a.trigger_config?.course && <span className="chip xs"> {a.trigger_config.course}</span>}
                  {a.trigger_config?.tag && <span className="chip xs"> {a.trigger_config.tag}</span>}
                  {a.trigger_config?.days && <span className="muted xs"> {a.trigger_config.days} วัน</span>}
                </td>
                <td>{(a.steps || []).length} ข้อความ</td>
                <td>{a.runs || 0}</td>
                <td className="row">
                  <button className="xs" onClick={() => setForm({ ...a, triggerConfig: a.trigger_config || {}, steps: a.steps?.length ? a.steps : [newStep()] })}>แก้ไข</button>
                  <button className="xs danger" onClick={() => confirm('ลบโฟลว์นี้?') && api.delAutomation(a.id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                </td>
              </tr>
            ))}
            {!list.length && <tr><td colSpan={6} className="muted center">ยังไม่มี — เช่น "หลังเพิ่มเพื่อน 1 วัน ส่งโปรโมชัน"</td></tr>}
          </tbody>
        </table>
        <p className="muted xs">ระบบเช็คทุก 5 นาที — จะข้าม user ที่ unfollow ไปแล้ว · ต้องตั้ง Webhook URL</p>
      </section>

      {form && (
        <div className="modal-bg" onClick={() => setForm(null)}>
          <div className="modal" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>{form.id ? 'แก้ไขโฟลว์' : 'โฟลว์ใหม่'}</h3><button className="xs" onClick={() => setForm(null)}>✕</button></div>

            <label className="sm">ชื่อ</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <label className="sm">เริ่มเมื่อ</label>
            <select value={form.trigger}
                    onChange={(e) => setForm({ ...form, trigger: e.target.value, triggerConfig: {} })}>
              {Object.entries(TRIGGERS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>

            {form.trigger === 'slip_verified' && (
              <>
                <label className="sm">เฉพาะหลักสูตร (เว้นว่าง = ทุกหลักสูตร)</label>
                <input placeholder="FC / IC / PC / AC" value={form.triggerConfig.course || ''}
                       onChange={(e) => setForm({ ...form, triggerConfig: { ...form.triggerConfig, course: e.target.value.trim().toUpperCase() || undefined } })} />
              </>
            )}
            {form.trigger === 'tag_added' && (
              <>
                <label className="sm">เมื่อถูกใส่ tag นี้ *</label>
                <input placeholder="เช่น paid-FC" value={form.triggerConfig.tag || ''}
                       onChange={(e) => setForm({ ...form, triggerConfig: { ...form.triggerConfig, tag: e.target.value.trim() } })} />
              </>
            )}
            {form.trigger === 'inactive' && (
              <>
                <label className="sm">ไม่ทักแชทกี่วัน</label>
                <input type="number" style={{ width: 90 }} value={form.triggerConfig.days || 14}
                       onChange={(e) => setForm({ ...form, triggerConfig: { ...form.triggerConfig, days: +e.target.value || 14 } })} />
                <p className="muted xs">เช็คทุก 5 นาที · คนที่หายไปเกิน (วัน+30) จะไม่ถูกดึง · แต่ละคนเข้าโฟลว์ครั้งเดียว</p>
              </>
            )}

            <label className="row"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> เปิดใช้</label>

            {form.steps.map((s, i) => (
              <div key={i} className="card" style={{ padding: 12, marginTop: 10, background: 'var(--panel-2)' }}>
                <div className="row spread">
                  <b className="sm">ขั้นที่ {i + 1}</b>
                  {form.steps.length > 1 && <button className="xs" onClick={() => setForm({ ...form, steps: form.steps.filter((_, j) => j !== i) })}>ลบขั้น</button>}
                </div>
                <div className="row wrap">
                  <span className="sm muted">รอ</span>
                  <input type="number" style={{ width: 70 }} value={s.delayHours}
                         onChange={(e) => setStep(i, { delayHours: +e.target.value })} /> ชม.
                  <input type="number" style={{ width: 60 }} value={s.delayMinutes}
                         onChange={(e) => setStep(i, { delayMinutes: +e.target.value })} /> นาที
                  <span className="muted xs">{i === 0 ? `(นับจาก "${trigLabel(form.trigger)}")` : '(นับจากขั้นก่อนหน้า)'}</span>
                </div>
                <div className="row spread" style={{ marginTop: 6 }}>
                  <span className="sm">ข้อความ ({s.messages.length}/5)</span>
                  <div className="row">
                    <button className="xs primary" onClick={() => setGallery(i)}>📚</button>
                    <button className="xs" disabled={s.messages.length >= 5}
                            onClick={() => setStep(i, { messages: [...s.messages, blank('text')] })}>+ ข้อความ</button>
                  </div>
                </div>
                {s.messages.map((m, j) => (
                  <MessageEditor key={j} index={j} msg={m}
                                 onChange={(nm) => setStep(i, { messages: s.messages.map((x, k) => k === j ? nm : x) })}
                                 onRemove={() => setStep(i, { messages: s.messages.filter((_, k) => k !== j) })} />
                ))}
                <div className="phone"><div className="phone-body">
                  {s.messages.map((m, j) => <MessagePreview key={j} msg={m} />)}
                </div></div>
              </div>
            ))}
            <button className="sm" onClick={() => setForm({ ...form, steps: [...form.steps, newStep()] })}>+ เพิ่มขั้นตอน</button>
            <div style={{ marginTop: 12 }}>
              <button className="primary" onClick={save} disabled={busy}>{busy && <InlineSpinner />}บันทึกโฟลว์</button>
            </div>
          </div>
        </div>
      )}

      {gallery != null && (
        <TemplateGallery onClose={() => setGallery(null)}
          onPick={(msgs) => setStep(gallery, { messages: msgs.slice(0, 5) })} />
      )}
    </div>
  )
}
