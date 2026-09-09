import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'

const SOURCE_LABEL = {
  sync: 'sync (เว็บ)',
  cron: 'sync (cron)',
  link: 'assign (เว็บ)',
  unlink: 'unlink (เว็บ)',
  enforce: 'enforce (cron)',
  slip: 'ส่งสลิป (อัตโนมัติ)',
}

function menuLabel(id) {
  if (!id) return <span className="muted">— ไม่มีเมนู —</span>
  return <code className="mono xs">{id}</code>
}

export default function RichMenuHistory() {
  const t = useToast()
  const [params] = useSearchParams()
  const [uidFilter, setUidFilter] = useState(params.get('userId') || '')
  const [items, setItems] = useState(null)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const LIMIT = 100

  const load = async (nextOffset = 0, append = false) => {
    setBusy(true); setErr('')
    try {
      const qs = { limit: LIMIT, offset: nextOffset }
      if (uidFilter.trim()) qs.userId = uidFilter.trim()
      const r = await api.richmenuHistory(qs)
      setItems((prev) => (append ? [...(prev || []), ...r.items] : r.items))
      setTotal(r.total)
      setOffset(nextOffset)
    } catch (e) {
      setErr(e.message); setItems([]); t.err(e.message)
    } finally { setBusy(false) }
  }

  useEffect(() => { load(0, false) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <h1>ประวัติการเปลี่ยน Rich Menu</h1>
      <p className="muted sm">
        บันทึกทุกครั้งที่เมนูของ user เปลี่ยน ไม่ว่าจะจากการ sync/assign บนเว็บนี้ หรือจาก cron job
        (เก็บเฉพาะครั้งที่ค่าจริง ๆ เปลี่ยน ไม่ log ถ้าเช็คซ้ำแล้วเหมือนเดิม)
      </p>

      <section className="card">
        <div className="row wrap">
          <input
            placeholder="กรองด้วย LINE userId (ขึ้นต้น U...)"
            value={uidFilter}
            onChange={(e) => setUidFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load(0, false)}
            style={{ minWidth: 280 }}
          />
          <button className="sm" disabled={busy} onClick={() => load(0, false)}>ค้นหา</button>
          {uidFilter && (
            <button className="sm" disabled={busy} onClick={() => { setUidFilter(''); load(0, false) }}>
              ล้างตัวกรอง
            </button>
          )}
        </div>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>รายการเปลี่ยนแปลง {total ? `(${total.toLocaleString()})` : ''}</h3>
        </div>
        {err && (
          <p className="err">
            โหลดไม่สำเร็จ: {err}
            {/richmenu_history|does not exist|PGRST|relation/i.test(err) &&
              <> — ตาราง <code>richmenu_history</code> ยังไม่ถูกสร้างใน DB (รัน migration 0003 ใน Supabase SQL Editor)</>}
          </p>
        )}
        {!items ? <Spinner /> : (
          <>
            <table>
              <thead>
                <tr>
                  <th>เวลา</th><th>userId</th><th>เมนูเดิม</th><th>เมนูใหม่</th>
                  <th>สถานะเดิม → ใหม่</th><th>ที่มา</th><th>โดย</th>
                </tr>
              </thead>
              <tbody>
                {items.map((h) => (
                  <tr key={h.id}>
                    <td className="muted sm">{new Date(h.created_at).toLocaleString('th-TH')}</td>
                    <td className="mono xs">{h.line_user_id}</td>
                    <td>{menuLabel(h.old_rich_menu_id)}</td>
                    <td>{menuLabel(h.new_rich_menu_id)}</td>
                    <td className="sm">{h.old_status || '–'} → {h.new_status || '–'}</td>
                    <td><span className="chip">{SOURCE_LABEL[h.source] || h.source}</span></td>
                    <td className="muted xs">{h.actor === 'cron' ? 'cron' : (h.actor || '–')}</td>
                  </tr>
                ))}
                {!items.length && (
                  <tr><td colSpan={7} className="muted">ยังไม่มีประวัติ{uidFilter ? 'สำหรับ userId นี้' : ''}</td></tr>
                )}
              </tbody>
            </table>
            {items.length < total && (
              <div className="row" style={{ justifyContent: 'center', marginTop: 12 }}>
                <button className="sm" disabled={busy} onClick={() => load(offset + LIMIT, true)}>
                  โหลดเพิ่ม ({items.length.toLocaleString()} / {total.toLocaleString()})
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
