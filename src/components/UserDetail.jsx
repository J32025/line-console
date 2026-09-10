import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, Spinner, Skeleton, InlineSpinner } from '../lib/ui.jsx'

export default function UserDetail({ uid, onClose, onSaved }) {
  const t = useToast()
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [tags, setTags] = useState('')
  const [custom, setCustom] = useState({})
  const [fields, setFields] = useState([])
  const [saving, setSaving] = useState(false)
  const [menus, setMenus] = useState([])
  const [selMenu, setSelMenu] = useState('')
  const [menuBusy, setMenuBusy] = useState(false)
  const [tl, setTl] = useState(null)
  const [notes, setNotes] = useState(null)
  const [newNote, setNewNote] = useState('')
  const [mergeInto, setMergeInto] = useState('')

  const loadDetail = () => api.userDetail(uid)
    .then((r) => {
      setD(r); setNote(r.user.note || ''); setTags((r.user.tags || []).join(', '))
      setCustom(r.user.custom || {})
    })
    .catch((e) => setErr(e.message))
  const loadNotes = () => api.userNotes(uid).then((r) => setNotes(r.notes)).catch(() => setNotes([]))

  useEffect(() => {
    setD(null); setErr(''); setTl(null); setNotes(null)
    api.fields().then((r) => setFields(r.fields)).catch(() => {})
    api.richmenus().then((r) => setMenus(r.menus || [])).catch(() => {})
    loadDetail()
    api.userTimeline(uid).then((r) => setTl(r.timeline)).catch(() => setTl([]))
    loadNotes()
  }, [uid])

  const quickPatch = async (patch) => {
    try { await api.updateUser(uid, patch); loadDetail(); onSaved?.() } catch (e) { t.err(e.message) }
  }
  const addNote = async () => {
    if (!newNote.trim()) return
    try { await api.addUserNote(uid, { body: newNote.trim() }); setNewNote(''); loadNotes(); api.userTimeline(uid).then((r) => setTl(r.timeline)) }
    catch (e) { t.err(e.message) }
  }
  const doMerge = async () => {
    if (!mergeInto.startsWith('U') || !confirm(`รวมบัญชีนี้เข้า ${mergeInto.slice(0, 12)}… ? (ย้ายทะเบียน/สลิป/งาน/โน้ต)`)) return
    try { const r = await api.mergeUsers({ from: uid, into: mergeInto.trim() }); t.ok('รวมแล้ว: ' + JSON.stringify(r.moved).slice(0, 80)); onClose() }
    catch (e) { t.err(e.message) }
  }

  const assignMenuToUser = async (mode) => {
    if (mode === 'link' && !selMenu) return t.err('เลือก rich menu ก่อน')
    setMenuBusy(true)
    try {
      await api.assignMenu({ mode, richMenuId: selMenu, target: 'list', userIds: [uid] })
      t.ok(mode === 'link' ? 'ผูกเมนูแล้ว' : 'ถอดเมนูแล้ว')
      await loadDetail()
      onSaved?.()
    } catch (e) { t.err(e.message) } finally { setMenuBusy(false) }
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.updateUser(uid, {
        note, tags: tags.split(',').map((s) => s.trim()).filter(Boolean), custom,
      })
      t.ok('บันทึกแล้ว'); onSaved?.()
    } catch (e) { t.err(e.message) } finally { setSaving(false) }
  }

  const u = d?.user
  const live = d?.live || {}
  const prof = live.profile

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row spread">
          <h3>รายละเอียดผู้ใช้</h3>
          <button className="xs" onClick={onClose}>ปิด ✕</button>
        </div>

        {err && <p className="err">{err}</p>}
        {!d && !err && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '12px 0' }}>
            <div className="row" style={{ gap: 14 }}>
              <Skeleton w={72} h={72} r={36} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <Skeleton w="55%" h={16} />
                <Skeleton w="80%" h={11} />
              </div>
            </div>
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} w="100%" h={12} />)}
            <div className="loading-text" style={{ textAlign: 'center', marginTop: 4 }}>
              <InlineSpinner />กำลังโหลดข้อมูลผู้ใช้…
            </div>
          </div>
        )}

        {u && (
          <>
            <div className="udetail-head">
              <img className="udetail-pic" alt=""
                   src={prof?.pictureUrl || u.picture_url || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2280%22%3E%3Crect width=%2280%22 height=%2280%22 fill=%22%23ddd%22/%3E%3C/svg%3E'} />
              <div>
                <div className="udetail-name">{prof?.displayName || u.display_name || <span className="muted">(ไม่มีชื่อ)</span>}</div>
                <div className="muted sm">{prof?.statusMessage || u.status_message || ''}</div>
                <div className="row" style={{ marginTop: 4 }}>
                  {u.is_following
                    ? <span className="chip ok">กำลังติดตาม</span>
                    : <span className="chip failed">ไม่ได้ติดตาม</span>}
                  {(prof?.language || u.language) && <span className="chip">{prof?.language || u.language}</span>}
                </div>
              </div>
            </div>

            <section className="card" style={{ padding: 12, margin: '10px 0' }}>
              <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
                <label className="sm">สถานะ&nbsp;
                  <select value={u.stage || ''} onChange={(e) => quickPatch({ stage: e.target.value })}>
                    <option value="">— ยังไม่กำหนด —</option>
                    {(d.stages || []).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                  </select>
                </label>
                <label className="sm"><input type="checkbox" checked={u.consent === true}
                  onChange={(e) => quickPatch({ consent: e.target.checked })} /> ยินยอมรับข่าวสาร</label>
              </div>
              <div className="row wrap" style={{ gap: 5, marginTop: 8 }}>
                {(d.registrations || []).map((r) => (
                  <span key={r.id} className={`chip ${r.paid ? 'ok' : ''}`}>{r.course_raw || r.course}{r.paid ? ' ✓' : ' ค้าง'}</span>
                ))}
                {(d.slips || []).slice(0, 3).map((s) => (
                  <span key={s.id} className={`chip xs ${s.status === 'verified' ? 'ok' : s.status === 'rejected' ? 'failed' : ''}`}>สลิป {s.status}</span>
                ))}
                {(d.open_tasks || []).length > 0 && <span className="chip xs failed">งานค้าง {d.open_tasks.length}</span>}
              </div>
            </section>

            <table className="kv">
              <tbody>
                <tr><th>userId</th><td className="mono xs">{u.line_user_id}</td></tr>
                <tr><th>ภาษา</th><td>{prof?.language || u.language || '–'}</td></tr>
                <tr><th>Rich Menu (DB)</th><td>{u.rich_menu_name || u.rich_menu_status || '–'}</td></tr>
                <tr><th>Rich Menu (สด)</th><td className="mono xs">{live.richMenuId || (live.error ? `err: ${live.error}` : '– ไม่มี')}</td></tr>
                <tr><th>เปลี่ยนเมนู</th><td>
                  <div className="row wrap" style={{ gap: 6 }}>
                    <select value={selMenu} onChange={(e) => setSelMenu(e.target.value)} disabled={menuBusy}>
                      <option value="">— เลือก rich menu —</option>
                      {menus.map((m) => (
                        <option key={m.richMenuId} value={m.richMenuId}>{m.name}</option>
                      ))}
                    </select>
                    <button className="xs primary" disabled={menuBusy || !selMenu} onClick={() => assignMenuToUser('link')}>
                      {menuBusy && <InlineSpinner />}ผูกเมนูนี้
                    </button>
                    <button className="xs" disabled={menuBusy} onClick={() => assignMenuToUser('unlink')}>ถอดเมนู</button>
                  </div>
                </td></tr>
                <tr><th></th><td>
                  <a className="sm" href={`/richmenus/history?userId=${u.line_user_id}`} target="_blank" rel="noreferrer">
                    ดูประวัติการเปลี่ยน Rich Menu ↗
                  </a>
                </td></tr>
                <tr><th>ที่มา</th><td>{u.source}</td></tr>
                <tr><th>follow / block</th><td>{u.follow_count ?? 0} ครั้ง / บล็อก {u.block_count ?? 0} ครั้ง</td></tr>
                <tr><th>เพิ่มเพื่อนครั้งแรก</th><td className="muted sm">{fmt(u.first_followed_at)}</td></tr>
                <tr><th>follow ล่าสุด</th><td className="muted sm">{fmt(u.followed_at)}</td></tr>
                {u.unfollowed_at && <tr><th>unfollow ล่าสุด</th><td className="muted sm">{fmt(u.unfollowed_at)}</td></tr>}
                <tr><th>เห็นในระบบครั้งแรก</th><td className="muted sm">{fmt(u.first_seen_at)}</td></tr>
                <tr><th>event ล่าสุด</th><td className="muted sm">{fmt(u.last_event_at)}</td></tr>
              </tbody>
            </table>

            {d.follow_history?.length > 0 && (
              <>
                <h4 className="sm">ประวัติ follow/unfollow</h4>
                <div className="udetail-events">
                  {d.follow_history.map((f, i) => (
                    <div key={i} className="row" style={{ fontSize: 12 }}>
                      <span className={`chip ${f.action === 'follow' ? 'ok' : 'failed'}`}>
                        {f.action === 'follow' ? (f.is_unblocked ? 'เพิ่มใหม่ (unblock)' : 'เพิ่มเพื่อน') : 'บล็อก/ลบ'}
                      </span>
                      <span className="muted xs" style={{ marginLeft: 'auto' }}>{fmt(f.event_ts)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}

            <div className="udetail-edit">
              <label className="sm">Tags (คั่นด้วย ,)</label>
              <input value={tags} onChange={(e) => setTags(e.target.value)} />
              {fields.map((f) => (
                <div key={f.key}>
                  <label className="sm">{f.label}</label>
                  {f.type === 'select' ? (
                    <select value={custom[f.key] || ''} onChange={(e) => setCustom({ ...custom, [f.key]: e.target.value })}>
                      <option value="">—</option>
                      {(f.options || []).map((o) => <option key={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                           value={custom[f.key] || ''} onChange={(e) => setCustom({ ...custom, [f.key]: e.target.value })} />
                  )}
                </div>
              ))}
              <label className="sm">Note</label>
              <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="primary sm" onClick={save} disabled={saving}>{saving && <InlineSpinner />}บันทึก</button>
            </div>

            <h4 className="sm">โน้ต / บันทึก {notes ? `(${notes.length})` : ''}</h4>
            <div className="row" style={{ gap: 6 }}>
              <input value={newNote} onChange={(e) => setNewNote(e.target.value)}
                     onKeyDown={(e) => e.key === 'Enter' && addNote()} placeholder="พิมพ์โน้ต แล้ว Enter" />
              <button className="xs primary" onClick={addNote}>+</button>
            </div>
            <div className="udetail-events">
              {(notes || []).map((n) => (
                <div key={n.id} className="row" style={{ fontSize: 12, alignItems: 'flex-start' }}>
                  <span style={{ flex: 1 }}>{n.body}</span>
                  <span className="muted xs">{n.author} · {fmt(n.created_at)}</span>
                  <button className="xs" onClick={() => api.delUserNote(uid, n.id).then(loadNotes)}>✕</button>
                </div>
              ))}
              {notes && !notes.length && <p className="muted xs">ยังไม่มีโน้ต</p>}
            </div>

            <h4 className="sm">ไทม์ไลน์ {tl ? `(${tl.length})` : ''}</h4>
            <div className="udetail-events" style={{ maxHeight: 280, overflowY: 'auto' }}>
              {!tl ? <InlineSpinner /> : tl.map((e, i) => (
                <div key={i} className="row" style={{ fontSize: 12, alignItems: 'flex-start' }}>
                  <span className="chip xs">{e.kind}</span>
                  <span style={{ flex: 1 }}>{e.text}</span>
                  <span className="muted xs">{fmt(e.at)}</span>
                </div>
              ))}
              {tl && !tl.length && <p className="muted xs">ยังไม่มีกิจกรรม</p>}
            </div>

            <details style={{ marginTop: 10 }}>
              <summary className="muted sm">รวมบัญชีซ้ำ (merge)</summary>
              <div className="row" style={{ gap: 6, marginTop: 6 }}>
                <input className="mono" value={mergeInto} onChange={(e) => setMergeInto(e.target.value)} placeholder="userId ปลายทาง U..." />
                <button className="xs danger" onClick={doMerge}>รวม</button>
              </div>
              <p className="muted xs">ย้ายทะเบียน/สลิป/งาน/โน้ต/ข้อความ ของคนนี้ไปบัญชีปลายทาง แล้วปิดบัญชีนี้</p>
            </details>
          </>
        )}
      </div>
    </div>
  )
}

const fmt = (s) => (s ? new Date(s).toLocaleString('th-TH') : '–')
