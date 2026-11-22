import { useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../lib/ui.jsx'

const n = (v) => (v ?? 0).toLocaleString()

// ตรวจ/ซ่อมกรณี "ส่งสลิปแล้วเมนู แล้วพบกัน ไม่เปลี่ยน" — ตรวจอ่านอย่างเดียว, ซ่อมต้องกดยืนยัน
export default function SlipMenuHealth() {
  const t = useToast()
  const [open, setOpen] = useState(false)
  const [d, setD] = useState(null)
  const [rep, setRep] = useState(null)
  const [busy, setBusy] = useState('')

  async function diagnose() {
    setBusy('diag')
    try { setD(await api.slipMenuDiagnose()); setRep(null) } catch (e) { t.err(e.message) } finally { setBusy('') }
  }
  async function repair(apply) {
    if (apply && !window.confirm('สลับเมนู "หลังส่งสลิป" ให้คนที่ส่งสลิปแล้วแต่ไม่เคยได้เมนูนี้ ทีละชุดไม่เกิน 60 คน — ยืนยัน?')) return
    setBusy(apply ? 'apply' : 'dry')
    try {
      const r = await api.slipMenuRepair(apply)
      setRep(r)
      if (apply) t.ok(`สลับแล้ว ${n(r.linked)} คน · ล้มเหลว ${n(r.failed)} · เหลืออีก ${n(r.remaining_after)}`)
    } catch (e) { t.err(e.message) } finally { setBusy('') }
  }

  const problems = []
  if (d) {
    if (d.menu_exists_in_line === false) problems.push('ไม่พบเมนูปลายทางใน LINE (ID ผิดหรือถูกลบ) — ตั้ง SLIP_SUCCESS_RICHMENU_ID ใหม่')
    if (d.enforce_menu_env) problems.push('เปิด ENFORCE_RICHMENU_ID อยู่ — อาจดึงผู้ใช้กลับเมนูเดิม')
    if (d.slip_users_never_received_but_following > 0) problems.push(`${n(d.slip_users_never_received_but_following)} คนส่งสลิปแล้วแต่ไม่เคยได้เมนูนี้ — กด “ซ่อม” ได้`)
    if ((d.jobs_by_status?.failed || 0) > 0) problems.push(`งานตรวจสลิปล้มเหลว ${n(d.jobs_by_status.failed)} งาน`)
    if ((d.jobs_by_status?.pending || 0) > 0) problems.push(`งานตรวจสลิปค้างรอ ${n(d.jobs_by_status.pending)} งาน (เก่าสุด ${d.jobs_oldest_pending || '-'})`)
    if (d.slip_link_failures_recent > 0) problems.push(`สั่งผูกเมนูไม่สำเร็จล่าสุด ${n(d.slip_link_failures_recent)} ครั้ง รหัส ${JSON.stringify(d.slip_link_failure_codes)}`)
    if (d.errors) problems.push('อ่านข้อมูลบางส่วนไม่ได้: ' + JSON.stringify(d.errors))
  }

  return (
    <section className="card">
      <div className="row spread">
        <h3>ตรวจเมนูหลังส่งสลิป</h3>
        <button className="sm" onClick={() => { setOpen(!open); if (!open && !d) diagnose() }}>{open ? 'ซ่อน' : 'เปิด'}</button>
      </div>
      {open && (
        <div>
          <div className="row">
            <button className="sm primary" onClick={diagnose} disabled={!!busy}>{busy === 'diag' ? 'กำลังตรวจ…' : 'ตรวจใหม่'}</button>
            <button className="sm" onClick={() => repair(false)} disabled={!!busy}>ซ่อม (ดูตัวอย่าง ไม่สลับจริง)</button>
            <button className="sm" onClick={() => repair(true)} disabled={!!busy || !d || !d.slip_users_never_received_but_following}>ซ่อมจริง</button>
          </div>
          {d && (
            <>
              {problems.length ? (
                <ul>{problems.map((p, i) => <li key={i}>⚠️ {p}</li>)}</ul>
              ) : <p>✅ ไม่พบความผิดปกติ</p>}
              <table>
                <tbody>
                  <tr><td>เมนูปลายทาง</td><td>{d.menu_name || '-'} <small>{d.richMenuId}</small> {d.menu_exists_in_line === false ? '❌ ไม่พบใน LINE' : '✔ มีอยู่'}</td></tr>
                  <tr><td>คนที่เคยส่งสลิป</td><td>{n(d.slip_users)} (ยังเป็นเพื่อน {n(d.slip_users_following)} · เลิกติดตาม {n(d.slip_users_not_following)} · ไม่มีใน line_users {n(d.slip_users_not_in_line_users)})</td></tr>
                  <tr><td>ตอนนี้อยู่บนเมนูนี้</td><td>{n(d.slip_users_on_menu_now)}</td></tr>
                  <tr><td>ไม่เคยได้เมนูนี้เลย</td><td><b>{n(d.slip_users_never_received_menu)}</b> (ยังเป็นเพื่อน {n(d.slip_users_never_received_but_following)})</td></tr>
                  <tr><td>ได้เมนูนี้ แยกตามที่มา</td><td>{JSON.stringify(d.menu_assigned_by_source)}</td></tr>
                  <tr><td>สลิปทั้งหมด</td><td>{n(d.slips_total)} {JSON.stringify(d.slips_by_status)}</td></tr>
                  <tr><td>สลิป 7 วันล่าสุด</td><td>{JSON.stringify(d.slips_last7d_by_status)}</td></tr>
                  <tr><td>คิวงานสลิป</td><td>{JSON.stringify(d.jobs_by_status)} {d.jobs_top_errors?.length ? ' · error: ' + JSON.stringify(d.jobs_top_errors) : ''}</td></tr>
                  <tr><td>ทะเบียนยังไม่จ่าย</td><td>{n(d.registrations_unpaid)} จาก {n(d.registrations_total)} (มีสลิปแล้ว {n(d.unpaid_with_slip)} · ไม่มีสลิป {n(d.unpaid_without_slip)})</td></tr>
                </tbody>
              </table>
            </>
          )}
          {rep && (
            <p>
              ผลซ่อม{rep.applied ? '' : ' (ตัวอย่าง)'}: เข้าข่าย {n(rep.never_received_candidates)} · ชุดนี้ {n(rep.batch)} ·
              {rep.applied ? ` สลับแล้ว ${n(rep.linked)} · ล้มเหลว ${n(rep.failed)}` : ` จะสลับ ${n(rep.would_link)}`} ·
              อยู่บนเมนูแล้ว {n(rep.already_on_menu)} · เหลือ {n(rep.remaining_after)}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
