import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, useToast } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'
import TemplateGallery from '../components/TemplateGallery.jsx'

const EMPTY = { data: '', label: '', match: 'exact', enabled: true, messages: [blank('text')] }

function ClickStats() {
  const t = useToast()
  const [days, setDays] = useState(30)
  const [sum, setSum] = useState(null)
  const [pick, setPick] = useState(null)
  const [detail, setDetail] = useState(null)
  useEffect(() => { setSum(null); api.postbackClicks(days).then(setSum).catch((e) => t.err(e.message)) }, [days]) // eslint-disable-line
  const open = (data) => { setPick(data); setDetail(null); api.postbackClicks(days, data).then(setDetail).catch((e) => t.err(e.message)) }
  const csv = () => {
    const rows = [['userId', 'ชื่อ', 'จำนวนครั้ง', 'ล่าสุด'], ...detail.users.map((u) => [u.line_user_id, u.display_name || '', u.clicks, u.last])]
    const body = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob(['﻿' + body], { type: 'text/csv;charset=utf-8' }))
    a.download = 'postback-clicks.csv'; a.click()
  }
  return (
    <section className="card">
      <div className="row spread" style={{ alignItems: 'center' }}>
        <h3>📊 สรุปการกดปุ่ม (ทุกที่)</h3>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[7, 30, 90, 365].map((d) => <option key={d} value={d}>{d} วัน</option>)}
        </select>
      </div>
      {!sum ? <Spinner /> : (
        <>
          <p className="muted sm">กด {sum.total_clicks.toLocaleString()} ครั้ง · {sum.unique_users.toLocaleString()} คน — คลิกที่ปุ่มเพื่อดูรายชื่อคนที่กด</p>
          <table>
            <thead><tr><th>ปุ่ม (data)</th><th>ครั้ง</th><th>คน</th><th>ล่าสุด</th></tr></thead>
            <tbody>
              {sum.buttons.map((b) => (
                <tr key={b.data} onClick={() => open(b.data)} style={{ cursor: 'pointer', fontWeight: pick === b.data ? 600 : 400 }}>
                  <td>{b.data}</td><td>{b.clicks}</td><td>{b.users}</td><td className="muted sm">{new Date(b.last).toLocaleString('th-TH')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {pick && (
        <div style={{ marginTop: 12 }}>
          <div className="row spread"><b>ผู้กด: {pick}</b>{detail && <button className="sm" onClick={csv}>ดาวน์โหลด CSV</button>}</div>
          {!detail ? <Spinner /> : (
            <table>
              <thead><tr><th>ชื่อ</th><th>userId</th><th>ครั้ง</th><th>ล่าสุด</th></tr></thead>
              <tbody>{detail.users.map((u) => (
                <tr key={u.line_user_id}><td>{u.display_name || '-'}</td><td className="muted sm">{u.line_user_id}</td><td>{u.clicks}</td>
                  <td className="muted sm">{new Date(u.last).toLocaleString('th-TH')}</td></tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}
    </section>
  )
}

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

      <ClickStats />

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
