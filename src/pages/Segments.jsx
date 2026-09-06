import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'

const EMPTY = { name: '', filter: { following: 'true', tag: '', menu: '', source: '' } }

export default function Segments() {
  const t = useToast()
  const [segs, setSegs] = useState(null)
  const [menus, setMenus] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)

  const load = () => api.segments().then((d) => setSegs(d.segments)).catch((e) => t.err(e.message))
  useEffect(() => {
    load()
    api.richmenuUsage().then((d) => setMenus(d.items.filter((i) => i.richMenuId))).catch(() => {})
  }, [])

  const setF = (k, v) => setForm((s) => ({ ...s, filter: { ...s.filter, [k]: v } }))

  const save = async () => {
    if (!form.name.trim()) return t.err('ตั้งชื่อกลุ่มก่อน')
    setBusy(true)
    try {
      const f = { ...form.filter }
      Object.keys(f).forEach((k) => f[k] === '' && delete f[k])
      const r = await api.saveSegment({ id: form.id, name: form.name, filter: f })
      t.ok(`บันทึกแล้ว — ${r.count.toLocaleString()} คน`)
      setForm(EMPTY); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const recount = async (s) => {
    try { const r = await api.segmentCount(s.id); t.ok(`${s.name}: ${r.count.toLocaleString()} คน`); load() }
    catch (e) { t.err(e.message) }
  }

  if (!segs) return <Spinner />

  return (
    <div>
      <h1>กลุ่มเป้าหมาย (Segments)</h1>

      <section className="card">
        <h3>{form.id ? 'แก้ไขกลุ่ม' : 'สร้างกลุ่มใหม่'}</h3>
        <input placeholder="ชื่อกลุ่ม เช่น 'ลงทะเบียนแล้ว' " value={form.name}
               onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <div className="row wrap" style={{ marginTop: 8 }}>
          <label>ติดตาม:&nbsp;
            <select value={form.filter.following} onChange={(e) => setF('following', e.target.value)}>
              <option value="true">กำลังติดตาม</option>
              <option value="false">ไม่ติดตาม</option>
              <option value="">ทั้งหมด</option>
            </select>
          </label>
          <label>Rich Menu:&nbsp;
            <select value={form.filter.menu} onChange={(e) => setF('menu', e.target.value)}>
              <option value="">ไม่กรอง</option>
              <option value="none">ไม่มีเมนู</option>
              {menus.map((m) => <option key={m.richMenuId} value={m.richMenuId}>{m.name} ({m.count})</option>)}
            </select>
          </label>
          <input placeholder="tag" value={form.filter.tag} onChange={(e) => setF('tag', e.target.value)} style={{ width: 120 }} />
          <input placeholder="source" value={form.filter.source} onChange={(e) => setF('source', e.target.value)} style={{ width: 120 }} />
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="primary" onClick={save} disabled={busy}>บันทึกกลุ่ม</button>
          {form.id && <button onClick={() => setForm(EMPTY)}>ยกเลิก</button>}
        </div>
      </section>

      <section className="card">
        <h3>กลุ่มที่บันทึกไว้ ({segs.length})</h3>
        <table>
          <thead><tr><th>ชื่อ</th><th>เงื่อนไข</th><th>จำนวน</th><th></th></tr></thead>
          <tbody>
            {segs.map((s) => (
              <tr key={s.id}>
                <td><b>{s.name}</b></td>
                <td className="muted xs">{JSON.stringify(s.filter)}</td>
                <td>{s.last_count?.toLocaleString() ?? '–'}</td>
                <td className="row">
                  <button className="xs" onClick={() => recount(s)}>นับใหม่</button>
                  <button className="xs" onClick={() => setForm({ id: s.id, name: s.name, filter: { following: 'true', tag: '', menu: '', source: '', ...s.filter } })}>แก้</button>
                  <button className="xs danger" onClick={() => confirm('ลบกลุ่ม?') && api.delSegment(s.id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                </td>
              </tr>
            ))}
            {!segs.length && <tr><td colSpan={4} className="muted center">ยังไม่มีกลุ่ม</td></tr>}
          </tbody>
        </table>
        <p className="muted xs">ใช้กลุ่มพวกนี้ได้ในหน้า "ส่งข้อความ" และ "Rich Menu → ผูกเป็นชุด"</p>
      </section>
    </div>
  )
}
