import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../lib/ui.jsx'

export default function UserDetail({ uid, onClose, onSaved }) {
  const t = useToast()
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [tags, setTags] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setD(null); setErr('')
    api.userDetail(uid)
      .then((r) => { setD(r); setNote(r.user.note || ''); setTags((r.user.tags || []).join(', ')) })
      .catch((e) => setErr(e.message))
  }, [uid])

  const save = async () => {
    setSaving(true)
    try {
      await api.updateUser(uid, { note, tags: tags.split(',').map((s) => s.trim()).filter(Boolean) })
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
        {!d && !err && <p className="muted">กำลังโหลด…</p>}

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

            <table className="kv">
              <tbody>
                <tr><th>userId</th><td className="mono xs">{u.line_user_id}</td></tr>
                <tr><th>Rich Menu (DB)</th><td>{u.rich_menu_name || u.rich_menu_status || '–'}</td></tr>
                <tr><th>Rich Menu (สด)</th><td className="mono xs">{live.richMenuId || (live.error ? `err: ${live.error}` : '– ไม่มี')}</td></tr>
                <tr><th>ที่มา</th><td>{u.source}</td></tr>
                <tr><th>เห็นครั้งแรก</th><td className="muted sm">{fmt(u.first_seen_at)}</td></tr>
                <tr><th>follow เมื่อ</th><td className="muted sm">{fmt(u.followed_at)}</td></tr>
                {u.unfollowed_at && <tr><th>unfollow เมื่อ</th><td className="muted sm">{fmt(u.unfollowed_at)}</td></tr>}
                <tr><th>อัปเดตล่าสุด</th><td className="muted sm">{fmt(u.updated_at)}</td></tr>
              </tbody>
            </table>

            <div className="udetail-edit">
              <label className="sm">Tags (คั่นด้วย ,)</label>
              <input value={tags} onChange={(e) => setTags(e.target.value)} />
              <label className="sm">Note</label>
              <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="primary sm" onClick={save} disabled={saving}>บันทึก</button>
            </div>

            <h4 className="sm">ประวัติ event ({d.events.length})</h4>
            <div className="udetail-events">
              {d.events.map((e, i) => (
                <div key={i} className="row" style={{ fontSize: 12 }}>
                  <span className={`chip ${e.event_type}`}>{e.event_type}</span>
                  <span>{e.text || e.message_type || ''}</span>
                  <span className="muted xs" style={{ marginLeft: 'auto' }}>{fmt(e.created_at)}</span>
                </div>
              ))}
              {!d.events.length && <p className="muted xs">ยังไม่มี event (ต้องตั้ง webhook)</p>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const fmt = (s) => (s ? new Date(s).toLocaleString('th-TH') : '–')
