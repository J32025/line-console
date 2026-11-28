import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { InlineSpinner, useToast } from '../lib/ui.jsx'

const FIELDS = [
  ['deadline', 'กำหนดปิดรับสมัคร / ชำระเงิน', 'ระบบไม่มีข้อมูลนี้ — ถ้าเว้นว่าง จะบอกผู้ถามว่าส่งให้แอดมินและแจ้งเตือนคุณ'],
  ['access', 'ทางเข้าเรียน / ระบบข้อสอบ / Pre-test', 'ต่อท้ายคำตอบที่ระบบบอกสถานะของผู้ถามแล้ว'],
  ['start', 'ข้อความเรื่องวันเริ่มติว (เสริม)', 'ระบบแสดงวันเริ่มจากหน้า “คลาส” ให้เอง ช่องนี้ไว้ใส่ข้อมูลเพิ่ม หรือกรณียังไม่มีคลาส'],
  ['contact', 'ข้อความเมื่อขอติดต่อแอดมิน (เสริม)', 'เว้นว่างได้ มีข้อความมาตรฐานให้ และแจ้งเตือนคุณเสมอ'],
]
const INTENT = { price: 'ค่าลงทะเบียน', start: 'วันเริ่มติว', deadline: 'ปิดรับสมัคร', status: 'สถานะ/สลิป', access: 'เข้าเรียน/ข้อสอบ', contact: 'ติดต่อแอดมิน', urgent: 'ร้องเรียน/เร่งด่วน' }

// ตั้งค่า + ทดลองคำตอบอัตโนมัติอัจฉริยะ (ทดลอง = ไม่ส่งข้อความและไม่แจ้งเตือน)
export default function SmartAnswers() {
  const t = useToast()
  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')
  const [uid, setUid] = useState('')
  const [res, setRes] = useState(null)

  useEffect(() => {
    if (open && !cfg) api.smartAnswersConfig().then(setCfg).catch((e) => t.err(e.message))
  }, [open]) // eslint-disable-line

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }))
  const save = async () => {
    setBusy(true)
    try { await api.setSetting('smart_answers', cfg); t.ok('บันทึกแล้ว') }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }
  const test = async () => {
    setBusy(true)
    try { setRes(await api.smartAnswersTest(q, uid.trim(), cfg)) }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <section className="card">
      <div className="row spread">
        <h3>⚡ ตอบอัตโนมัติอัจฉริยะ</h3>
        <button className="sm" onClick={() => setOpen(!open)}>{open ? 'ซ่อน' : 'ตั้งค่า / ทดลอง'}</button>
      </div>
      <p className="muted sm">ตอบคำถามเรื่องค่าลงทะเบียน วันเริ่มติว ปิดรับสมัคร สถานะ/สลิป ทางเข้าเรียน และการติดต่อ จากข้อมูลจริงของผู้ถาม · กฎคีย์เวิร์ดของคุณยังมาก่อนเสมอ</p>
      {open && cfg && (
        <>
          <label className="sm"><input type="checkbox" checked={cfg.enabled} onChange={(e) => set('enabled', e.target.checked)} /> เปิดใช้งาน</label><br />
          <label className="sm"><input type="checkbox" checked={cfg.share_class_links} onChange={(e) => set('share_class_links', e.target.checked)} /> ส่งลิงก์ห้องเรียน/เอกสารให้อัตโนมัติ (เฉพาะคนที่จ่ายแล้วและถูกจัดเข้าคลาสแล้ว)</label>
          {FIELDS.map(([k, label, hint]) => (
            <div key={k} style={{ marginTop: 10 }}>
              <b className="sm">{label}</b>
              <div className="muted xs">{hint}</div>
              <textarea rows={2} maxLength={1500} value={cfg[k]} onChange={(e) => set(k, e.target.value)} />
            </div>
          ))}
          <button className="primary sm" onClick={save} disabled={busy}>{busy && <InlineSpinner />}บันทึก</button>

          <div style={{ borderTop: '1px solid var(--border)', marginTop: 14, paddingTop: 10 }}>
            <b className="sm">ทดลองถาม</b>
            <div className="row wrap" style={{ gap: 8 }}>
              <input placeholder="เช่น ค่าติวเท่าไหร่คะ" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 2, minWidth: 220 }} />
              <input placeholder="userId (เว้นได้ = คนที่ยังไม่ลงทะเบียน)" value={uid} onChange={(e) => setUid(e.target.value)} style={{ flex: 1, minWidth: 220 }} />
              <button className="sm" onClick={test} disabled={busy || !q.trim()}>ดูคำตอบ</button>
            </div>
            {res && (res.matched ? (
              <div className="sm" style={{ marginTop: 8 }}>
                <div>จับได้เป็นเรื่อง: {res.intents.map((i) => INTENT[i] || i).join(', ')}{res.escalate ? ` · ⚠️ จะส่งต่อแอดมิน (${res.escalate})` : ''}</div>
                <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{res.message.text}</pre>
                <div className="muted xs">ปุ่ม: {(res.message.quickReply?.items || []).map((i) => i.action.label).join(' · ') || '-'}</div>
              </div>
            ) : <p className="muted sm">ข้อความนี้ระบบอัจฉริยะไม่รับตอบ — จะใช้กฎ fallback หรือ AI ตามเดิม</p>)}
            <p className="muted xs">ผลทดลองไม่รวมกฎคีย์เวิร์ดของคุณ ถ้ากฎใดตรง ข้อความจริงจะได้คำตอบจากกฎนั้น</p>
          </div>
        </>
      )}
    </section>
  )
}
