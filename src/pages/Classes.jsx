import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, useToast } from '../lib/ui.jsx'

const EMPTY = { course: '', name: '', cohort: '', start_date: '', end_date: '', schedule: '', zoom_url: '', materials_url: '', capacity: '', status: 'open', note: '' }

export default function Classes() {
  const t = useToast()
  const [list, setList] = useState(null)
  const [form, setForm] = useState(null)
  const [open, setOpen] = useState(null)   // class id
  const [busy, setBusy] = useState(false)

  const load = () => api.classes().then((d) => setList(d.classes)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    if (!form.course.trim()) return t.err('ใส่หลักสูตร')
    setBusy(true)
    try {
      await api.saveClass({ ...form, capacity: +form.capacity || null,
        start_date: form.start_date || null, end_date: form.end_date || null })
      t.ok('บันทึกแล้ว'); setForm(null); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="row spread wrap" style={{ alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>คลาส / รุ่น</h1>
        <button className="sm primary" onClick={() => setForm({ ...EMPTY })}>+ สร้างคลาส</button>
      </div>

      {!list ? <Spinner /> : (
        <div className="grid two">
          {list.map((c) => (
            <section className="card" key={c.id}>
              <div className="row spread">
                <div>
                  <b>{c.name || `${c.course} ${c.cohort || ''}`}</b>
                  <span className={`chip xs ${c.status === 'running' ? 'ok' : ''}`} style={{ marginLeft: 6 }}>{c.status}</span>
                </div>
                <span className="chip">{c.course}</span>
              </div>
              <div className="muted sm" style={{ margin: '4px 0' }}>
                {c.start_date && `เริ่ม ${c.start_date}`} {c.schedule && `· ${c.schedule}`}
              </div>
              <div className="row spread">
                <span className="sm">นักเรียน {c.enrolled || 0}{c.capacity ? ` / ${c.capacity}` : ''}</span>
                <div className="row">
                  <button className="xs" onClick={() => setOpen(c.id)}>เปิด</button>
                  <button className="xs" onClick={() => setForm({ ...EMPTY, ...c, capacity: c.capacity || '', start_date: c.start_date || '', end_date: c.end_date || '' })}>แก้</button>
                  <button className="xs danger" onClick={() => confirm('ลบคลาสนี้? (ปลดนักเรียนออก)') && api.delClass(c.id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                </div>
              </div>
            </section>
          ))}
          {!list.length && <p className="muted card center">ยังไม่มีคลาส</p>}
        </div>
      )}

      {form && (
        <div className="modal-bg" onClick={() => setForm(null)}>
          <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>{form.id ? 'แก้ไขคลาส' : 'คลาสใหม่'}</h3><button className="xs" onClick={() => setForm(null)}>✕</button></div>
            <div className="row wrap">
              <label className="sm" style={{ flex: 1 }}>หลักสูตร *<input value={form.course} onChange={(e) => setForm({ ...form, course: e.target.value.trim().toUpperCase() })} placeholder="FC70" /></label>
              <label className="sm" style={{ flex: 1 }}>รุ่น<input value={form.cohort} onChange={(e) => setForm({ ...form, cohort: e.target.value })} placeholder="รุ่น 3" /></label>
            </div>
            <label className="sm">ชื่อคลาส (แสดงผล)</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="FC70 รุ่น 3 (ก.พ. 70)" />
            <div className="row wrap">
              <label className="sm">วันเริ่ม<input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></label>
              <label className="sm">วันจบ<input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></label>
              <label className="sm">รับ (คน)<input type="number" style={{ width: 80 }} value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} /></label>
              <label className="sm">สถานะ
                <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="open">เปิดรับ</option><option value="running">กำลังเรียน</option><option value="closed">ปิด</option>
                </select>
              </label>
            </div>
            <label className="sm">ตารางเรียน</label>
            <input value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} placeholder="ทุกวันเสาร์ 9:00-16:00" />
            <label className="sm">ลิงก์ Zoom</label>
            <input value={form.zoom_url} onChange={(e) => setForm({ ...form, zoom_url: e.target.value })} />
            <label className="sm">ลิงก์เอกสาร</label>
            <input value={form.materials_url} onChange={(e) => setForm({ ...form, materials_url: e.target.value })} />
            <button className="primary" disabled={busy} onClick={save}>{busy && <InlineSpinner />}บันทึก</button>
          </div>
        </div>
      )}

      {open && <ClassDetail id={open} onClose={() => { setOpen(null); load() }} />}
    </div>
  )
}

function ClassDetail({ id, onClose }) {
  const t = useToast()
  const [d, setD] = useState(null)
  const [sess, setSess] = useState(1)
  const [pres, setPres] = useState({})
  const [msg, setMsg] = useState('เรียน {class} วันนี้ครับ\nZoom: {zoom}\nเอกสาร: {materials}')
  const [busy, setBusy] = useState('')

  const load = () => api.classDetail(id).then((r) => {
    setD(r)
    const p = {}
    r.roster.forEach((x) => { p[x.line_user_id] = r.attendance[x.line_user_id]?.[sess] ?? true })
    setPres(p)
  }).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [id]) // eslint-disable-line
  useEffect(() => {
    if (!d) return
    const p = {}
    d.roster.forEach((x) => { p[x.line_user_id] = d.attendance[x.line_user_id]?.[sess] ?? true })
    setPres(p)
  }, [sess]) // eslint-disable-line

  const assign = async (regId, mode) => {
    try { await api.classAssign(id, { registrationIds: [regId], mode }); load() } catch (e) { t.err(e.message) }
  }
  const saveAttendance = async () => {
    setBusy('att')
    try {
      await api.classAttendance(id, { session: sess, records: Object.entries(pres).map(([u, p]) => ({ line_user_id: u, present: p })) })
      t.ok(`บันทึกเช็คชื่อครั้งที่ ${sess}`); load()
    } catch (e) { t.err(e.message) } finally { setBusy('') }
  }
  const sendMsg = async () => {
    setBusy('msg')
    try { const r = await api.classMessage(id, msg); t.ok(`ส่งแล้ว ${r.sent} คน`) }
    catch (e) { t.err(e.message) } finally { setBusy('') }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 680 }} onClick={(e) => e.stopPropagation()}>
        <div className="row spread"><h3>{d?.class?.name || 'คลาส'}</h3><button className="xs" onClick={onClose}>✕</button></div>
        {!d ? <Spinner /> : (
          <>
            <p className="muted sm">{d.class.course} · {d.class.schedule || '–'} · Zoom: {d.class.zoom_url ? <a href={d.class.zoom_url} target="_blank" rel="noreferrer">ลิงก์</a> : '–'}</p>

            <h4 className="sm">เช็คชื่อ — ครั้งที่&nbsp;
              <select value={sess} onChange={(e) => setSess(+e.target.value)}>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </h4>
            <div className="table-scroll" style={{ maxHeight: 240 }}>
              <table>
                <tbody>
                  {d.roster.map((r) => (
                    <tr key={r.id}>
                      <td><label><input type="checkbox" checked={!!pres[r.line_user_id]}
                        onChange={(e) => setPres({ ...pres, [r.line_user_id]: e.target.checked })} /> {r.name || r.line_user_id.slice(0, 10)}</label></td>
                      <td className="sm muted">{r.paid ? 'จ่ายแล้ว' : 'ค้างจ่าย'}</td>
                      <td><button className="xs" onClick={() => assign(r.id, 'remove')}>เอาออก</button></td>
                    </tr>
                  ))}
                  {!d.roster.length && <tr><td className="muted">ยังไม่มีนักเรียน — เพิ่มจากรายการด้านล่าง</td></tr>}
                </tbody>
              </table>
            </div>
            <button className="sm primary" disabled={busy === 'att'} onClick={saveAttendance}>{busy === 'att' && <InlineSpinner />}บันทึกเช็คชื่อ</button>

            {d.available?.length > 0 && (
              <>
                <h4 className="sm">เพิ่มนักเรียน (ลงทะเบียนคอร์สนี้ ยังไม่เข้าคลาส)</h4>
                <div className="row wrap" style={{ gap: 4 }}>
                  {d.available.map((r) => (
                    <button key={r.id} className="xs" onClick={() => assign(r.id, 'add')}>+ {r.name || r.line_user_id.slice(0, 8)}</button>
                  ))}
                </div>
              </>
            )}

            <h4 className="sm">ส่งข้อความหาคลาสนี้ ({d.roster.length} คน)</h4>
            <p className="muted xs">ใช้ตัวแปร: {'{class} {zoom} {materials} {schedule} {start}'}</p>
            <textarea rows={4} value={msg} onChange={(e) => setMsg(e.target.value)} />
            <button className="primary sm" disabled={busy === 'msg' || !d.roster.length} onClick={sendMsg}>{busy === 'msg' && <InlineSpinner />}ส่ง</button>
          </>
        )}
      </div>
    </div>
  )
}
