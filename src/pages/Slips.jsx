import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { SkeletonCards, InlineSpinner, useToast } from '../lib/ui.jsx'

const TABS = [['new', 'ใหม่'], ['review', 'ต้องตรวจเอง'], ['verified', 'ผ่าน'], ['rejected', 'ไม่ผ่าน'], ['', 'ทั้งหมด']]

// เครื่องมือจัดการสลิปที่ค้าง: (1) ตรวจซ้ำ (2) คัดแยกรูปที่ไม่ใช่สลิป — ทั้งคู่ "เงียบ" ไม่ส่งข้อความหาลูกค้า
// หน้าเว็บเรียก API เป็นชุด ๆ (แต่ละชุดต้องจบใน ~60 วินาทีของ Vercel) แล้วรวมผลให้
function SlipTools({ onDone }) {
  const t = useToast()
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState(null)
  const [run, setRun] = useState(null)   // { kind, running, text }
  const cancel = useRef(false)

  const loadInfo = () => api.slipsMaintenance().then(setInfo).catch((e) => t.err(e.message))
  useEffect(() => { if (open && !info) loadInfo() }, [open]) // eslint-disable-line

  const reprocessCount = info ? info.never_processed + info.quota_retry : 0
  const finish = (kind, text, ok = true) => {
    setRun({ kind, running: false, text })
    ok ? t.ok(text) : t.err(text)
    loadInfo(); onDone()
  }

  const reprocess = async () => {
    if (!confirm(`ตรวจซ้ำสลิปที่ค้าง?\n\n• ${info.never_processed + info.quota_retry} ใบ เรียก EasySlip อ่านใหม่ (เหลือโควต้า ${info.easyslip_remaining ?? '?'} — กันไว้ ${info.easyslip_reserve} ให้สลิปใหม่)\n• ${info.rematch_offline} ใบ ประเมินใหม่จากผลอ่านเดิม (ไม่เสียโควต้า)\n\nถ้ายืนยันได้ จะ mark "จ่ายแล้ว" ในทะเบียน แต่ไม่ส่งข้อความ/ใบเสร็จหาลูกค้า`)) return
    cancel.current = false
    const tot = { verified: 0, review: 0, rejected: 0, error: 0, no_image: 0 }
    let done = 0, note = ''
    setRun({ kind: 'reprocess', running: true, text: 'กำลังเริ่ม…' })
    try {
      for (let i = 0; i < 12 && !cancel.current; i++) {
        const r = await api.slipsReprocess(25, i === 0)   // ประเมินซ้ำจากผลเดิมรอบแรกรอบเดียว กันวนใบเดิม
        Object.keys(tot).forEach((k) => { tot[k] += r.result?.[k] || 0 })
        done += r.processed || 0
        setRun({ kind: 'reprocess', running: true, text: `ทำแล้ว ${done} ใบ · ยืนยัน ${tot.verified} · ตรวจเอง ${tot.review} · ซ้ำ ${tot.rejected}…` })
        if (r.budget === 0) { note = ' — โควต้า EasySlip เหลือน้อย หยุดเพื่อกันไว้ให้สลิปใหม่'; break }
        if (!r.left || !r.processed) break
      }
      finish('reprocess', `ตรวจซ้ำ ${done} ใบ: ยืนยัน ${tot.verified} · ให้คนตรวจ ${tot.review} · ตีกลับ(ซ้ำ) ${tot.rejected}${tot.error ? ` · ผิดพลาด ${tot.error}` : ''}${note}${cancel.current ? ' — หยุดตามสั่ง' : ''}`)
    } catch (e) { finish('reprocess', e.message, false) }
  }

  const triage = async () => {
    if (!confirm(`คัดแยกรูปที่ไม่ใช่สลิป?\n\nEasySlip อ่าน QR ไม่ได้ ${info.triage_candidates} ใบ — Gemini จะดูทีละใบ (ใช้เวลา ~5 วินาที/ใบ เปิดหน้านี้ค้างไว้)\n• มั่นใจ ≥80% ว่าไม่ใช่สลิป → ย้ายไป "ไม่ผ่าน" (ย้อนกลับได้ รูปไม่หาย)\n• ดูเป็นสลิป → ยังค้างให้คนตรวจ แต่แนบยอด/ธนาคารที่อ่านได้ให้\nไม่ส่งข้อความหาลูกค้า`)) return
    cancel.current = false
    const tot = { rejected_not_slip: 0, annotated_slip: 0, left_unclear: 0, no_image: 0, error: 0 }
    let done = 0, offset = 0
    setRun({ kind: 'triage', running: true, text: 'กำลังเริ่ม…' })
    try {
      for (let i = 0; i < 20 && !cancel.current; i++) {
        const r = await api.slipsTriage(8, offset)
        Object.keys(tot).forEach((k) => { tot[k] += r.result?.[k] || 0 })
        done += r.processed || 0
        offset = r.next_offset || 0
        setRun({ kind: 'triage', running: true, text: `ดูแล้ว ${done}/${info.triage_candidates} ใบ · ไม่ใช่สลิป ${tot.rejected_not_slip} · น่าจะเป็นสลิป ${tot.annotated_slip}…` })
        if (!r.left || !r.processed) break
      }
      const unclear = tot.left_unclear + tot.no_image + tot.error
      finish('triage', `คัดแยก ${done} ใบ: ไม่ใช่สลิป ${tot.rejected_not_slip} · น่าจะเป็นสลิป (ให้คนตรวจ) ${tot.annotated_slip}${unclear ? ` · ตัดสินไม่ได้ ${unclear}` : ''}${cancel.current ? ' — หยุดตามสั่ง' : ''}`)
    } catch (e) { finish('triage', e.message, false) }
  }

  return (
    <section className="card">
      <div className="row spread">
        <b>🛠 เครื่องมือจัดการสลิปที่ค้าง</b>
        <button className="xs" onClick={() => setOpen((v) => !v)}>{open ? 'ซ่อน' : 'เปิด'}</button>
      </div>
      {open && (!info ? <p className="muted sm"><InlineSpinner /> กำลังนับ…</p> : (
        <>
          <p className="muted xs">ทำแบบเงียบ: ไม่ส่งข้อความ/ใบเสร็จ/สลับเมนูหาลูกค้า และไม่ลบรูปหรือข้อมูลใด ๆ</p>
          <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
            <button className="sm primary" disabled={run?.running || reprocessCount + info.rematch_offline === 0} onClick={reprocess}>
              🔁 ตรวจซ้ำ ({reprocessCount + info.rematch_offline} ใบ)
            </button>
            <span className="muted xs">
              ไม่เคยตรวจ {info.never_processed} · โควต้า EasySlip เต็มตอนนั้น {info.quota_retry} · ประเมินใหม่จากผลเดิม {info.rematch_offline}
            </span>
          </div>
          <div className="row wrap" style={{ gap: 8, alignItems: 'center', marginTop: 8 }}>
            <button className="sm primary" disabled={run?.running || info.triage_candidates === 0} onClick={triage}>
              🧹 คัดแยกรูปที่ไม่ใช่สลิป ({info.triage_candidates} ใบ)
            </button>
            <span className="muted xs">EasySlip อ่าน QR ไม่ได้ → ให้ Gemini แยกว่าเป็นสลิปจริงหรือรูปอื่น</span>
          </div>
          {run && (
            <p className="sm" style={{ marginTop: 8 }}>
              {run.running && <InlineSpinner />} {run.text}
              {run.running && <button className="xs" style={{ marginLeft: 8 }} onClick={() => { cancel.current = true }}>หยุด (หลังชุดนี้)</button>}
            </p>
          )}
        </>
      ))}
    </section>
  )
}

export default function Slips() {
  const t = useToast()
  const [list, setList] = useState(null)
  const [tab, setTab] = useState('new')
  const [newCount, setNewCount] = useState(0)
  const [zoom, setZoom] = useState(null)
  const [busy, setBusy] = useState(0)

  const load = () => api.slips(tab).then((d) => { setList(d.slips); setNewCount(d.new_count) }).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [tab]) // eslint-disable-line
  useEffect(() => { const i = setInterval(() => { if (!document.hidden) load() }, 30000); return () => clearInterval(i) }, [tab]) // eslint-disable-line

  const act = async (s, status, replyUser) => {
    setBusy(s.id)
    try {
      await api.updateSlip(s.id, { status, replyUser })
      t.ok(status === 'verified' ? 'ยืนยันแล้ว' : 'ปฏิเสธแล้ว')
      load()
    } catch (e) { t.err(e.message) } finally { setBusy(0) }
  }

  return (
    <div>
      <h1>สลิปโอนเงิน {newCount > 0 && <span className="chip failed">{newCount} ใหม่</span>}</h1>
      <SlipTools onDone={load} />
      <div className="row">
        {TABS.map(([v, l]) => <button key={v} className={tab === v ? 'sm primary' : 'sm'} onClick={() => setTab(v)}>{l}</button>)}
        <button className="sm" onClick={load}>รีเฟรช</button>
      </div>

      {!list ? <SkeletonCards count={6} /> : list.length === 0 ? (
        <p className="muted card center">ไม่มีสลิป{tab === 'new' ? 'ใหม่' : ''}</p>
      ) : (
        <div className="slip-grid">
          {list.map((s) => (
            <div key={s.id} className={`slip-card ${s.status}`}>
              {s.media_url
                ? <img src={s.media_url} alt="slip" onClick={() => setZoom(s.media_url)} />
                : <div className="slip-noimg">โหลดรูปไม่ได้</div>}
              <div className="slip-body">
                <div className="row spread">
                  <b className="sm ellipsis">{s.user?.display_name || s.line_user_id.slice(0, 10)}</b>
                  <span className={`chip ${s.status === 'verified' ? 'ok' : s.status === 'rejected' ? 'failed' : ''}`}>{s.status}</span>
                </div>
                {s.amount && <div className="sm">💰 {Number(s.amount).toLocaleString()} บาท {s.bank && `· ${s.bank}`}</div>}
                {s.expected_course && <span className="chip">{s.expected_course}{s.matched === true ? ' ✓' : s.matched === false ? ' ✗ยอดไม่ตรง' : ''}</span>}
                {s.ref && <div className="muted xs">ref: {s.ref}</div>}
                {s.auto_note && <div className="xs" style={{ color: s.status === 'verified' ? 'var(--primary-d)' : 'var(--warn)' }}>{s.auto_note}</div>}
                <div className="muted xs">{new Date(s.created_at).toLocaleString('th-TH')}</div>
                {(s.status === 'new' || s.status === 'review') && (
                  <div className="row" style={{ marginTop: 6 }}>
                    <button className="xs primary" disabled={busy === s.id} onClick={() => act(s, 'verified', true)}>
                      {busy === s.id ? <InlineSpinner /> : '✓'} ผ่าน + แจ้ง user
                    </button>
                    <button className="xs danger" disabled={busy === s.id} onClick={() => act(s, 'rejected', true)}>✕ ไม่ผ่าน</button>
                  </div>
                )}
                {s.status !== 'new' && s.status !== 'review' && s.reviewed_at && (
                  <div className="muted xs">ตรวจโดย {s.reviewed_by?.slice(0, 8)} · {new Date(s.reviewed_at).toLocaleString('th-TH')}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {zoom && (
        <div className="modal-bg" onClick={() => setZoom(null)}>
          <img src={zoom} alt="" style={{ maxWidth: '92vw', maxHeight: '92vh', borderRadius: 10 }} />
        </div>
      )}
    </div>
  )
}
