import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, useToast } from '../lib/ui.jsx'
import UserDetail from './UserDetail.jsx'

const PAGE = 50

// เปิดจากยอด "ใช้อยู่" ของ rich menu หนึ่งเมนู — ดูว่าใครถือเมนูนี้อยู่บ้าง
// เลือกได้ทีละคนหรือหลายคนพร้อมกัน แล้วสลับ/ถอดเมนูเป็นชุดได้เลย
export default function MenuUsersModal({ richMenuId, name, menus, onClose, onChanged }) {
  const t = useToast()
  const [rows, setRows] = useState(null)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(new Set())
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [detailUid, setDetailUid] = useState(null)
  const [changed, setChanged] = useState(false)

  const menuParam = richMenuId || 'none'

  const load = () => {
    setRows(null)
    api.users({ menu: menuParam, q, limit: PAGE, offset })
      .then((r) => { setRows(r.users); setTotal(r.total) })
      .catch((e) => t.err(e.message))
  }
  useEffect(() => { load() }, [offset, menuParam]) // eslint-disable-line
  useEffect(() => { setOffset(0) }, [q]) // eslint-disable-line

  const toggle = (uid) => setSel((s) => {
    const n = new Set(s)
    n.has(uid) ? n.delete(uid) : n.add(uid)
    return n
  })
  const toggleAllPage = () => setSel((s) => {
    const allOn = rows.every((u) => s.has(u.line_user_id))
    const n = new Set(s)
    rows.forEach((u) => (allOn ? n.delete(u.line_user_id) : n.add(u.line_user_id)))
    return n
  })

  const applyChange = async () => {
    if (!sel.size) return
    const label = target ? `เปลี่ยนเป็น "${menus.find((m) => m.richMenuId === target)?.name}"` : 'ถอดเมนู'
    if (!confirm(`${label} ให้ ${sel.size} คนที่เลือก?`)) return
    setBusy(true)
    try {
      const r = await api.assignMenu({
        mode: target ? 'link' : 'unlink', richMenuId: target || undefined,
        target: 'list', userIds: [...sel],
      })
      t.ok(`เสร็จ: สำเร็จ ${r.ok} / ล้มเหลว ${r.fail}`)
      setSel(new Set()); setChanged(true); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const close = () => { onClose(); if (changed) onChanged?.() }

  return (
    <div className="modal-bg" onClick={close}>
      <div className="modal" style={{ maxWidth: 720 }} onClick={(e) => e.stopPropagation()}>
        <div className="row spread">
          <h3>👥 ใช้เมนู "{name}" อยู่ ({total.toLocaleString()} คน)</h3>
          <button className="xs" onClick={close}>✕</button>
        </div>

        <input placeholder="ค้นชื่อ / userId" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 8 }} />

        {!rows ? <Spinner /> : (
          <>
            {!rows.length ? <p className="muted sm">ไม่มีใครอยู่ที่เมนูนี้{q ? ' (ตามคำค้นนี้)' : ''}</p> : (
              <table>
                <thead>
                  <tr>
                    <th><input type="checkbox" checked={rows.length > 0 && rows.every((u) => sel.has(u.line_user_id))} onChange={toggleAllPage} /></th>
                    <th>ผู้ใช้</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((u) => (
                    <tr key={u.line_user_id}>
                      <td><input type="checkbox" checked={sel.has(u.line_user_id)} onChange={() => toggle(u.line_user_id)} /></td>
                      <td>
                        <div className="row" style={{ alignItems: 'center', gap: 8 }}>
                          {u.picture_url && <img src={u.picture_url} alt="" className="avatar-xs" />}
                          <div>
                            <div>{u.display_name || '(ไม่มีชื่อ)'}</div>
                            <div className="muted xs mono">{u.line_user_id}</div>
                          </div>
                        </div>
                      </td>
                      <td><button className="xs" onClick={() => setDetailUid(u.line_user_id)}>ดู/แก้ทีละคน</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {total > PAGE && (
              <div className="row spread" style={{ marginTop: 8 }}>
                <button className="xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>‹ ก่อนหน้า</button>
                <span className="muted xs">{offset + 1}–{Math.min(offset + PAGE, total)} จาก {total.toLocaleString()}</span>
                <button className="xs" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>ถัดไป ›</button>
              </div>
            )}
          </>
        )}

        <div className="row wrap" style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 10, alignItems: 'center', gap: 8 }}>
          <b className="sm">เลือกอยู่ {sel.size} คน</b>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">— ถอดเมนู (ไม่มีเมนู) —</option>
            {menus.filter((m) => m.richMenuId !== richMenuId).map((m) => (
              <option key={m.richMenuId} value={m.richMenuId}>เปลี่ยนเป็น: {m.name}</option>
            ))}
          </select>
          <button className="primary sm" disabled={!sel.size || busy} onClick={applyChange}>
            {busy && <InlineSpinner />}ใช้กับที่เลือก
          </button>
        </div>
      </div>

      {detailUid && (
        <UserDetail uid={detailUid} onClose={() => setDetailUid(null)}
                    onSaved={() => { setChanged(true); load() }} />
      )}
    </div>
  )
}
