import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../lib/ui.jsx'
import UserDetail from '../components/UserDetail.jsx'

export default function Users() {
  const t = useToast()
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [following, setFollowing] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [importText, setImportText] = useState('')
  const [importTag, setImportTag] = useState('')
  const [detailUid, setDetailUid] = useState(null)
  const [progress, setProgress] = useState(null)
  const limit = 60

  const load = () => {
    setBusy(true)
    api.users({ q, following, limit, offset })
      .then((d) => { setRows(d.users); setTotal(d.total) })
      .catch((e) => t.err(e.message))
      .finally(() => setBusy(false))
  }
  useEffect(() => { load() }, [offset, following]) // eslint-disable-line

  const doImport = async () => {
    const ids = importText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)
    if (!ids.length) return
    setBusy(true)
    try {
      const r = await api.importUsers({ userIds: ids, tag: importTag || undefined })
      t.ok(`import: ใหม่ ${r.new} / ซ้ำ ${r.duplicate}`)
      setImportText(''); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  // ดึงโปรไฟล์ทั้งหมด — วนจนกว่า remaining = 0
  const fetchAllProfiles = async () => {
    setBusy(true)
    let done = 0, unfollow = 0
    try {
      for (let i = 0; i < 60; i++) {
        const r = await api.refreshProfiles({ target: 'missing', limit: 400 })
        done += r.profiles_fetched
        unfollow += r.not_following
        setProgress({ done, unfollow, remaining: r.remaining })
        if (r.remaining === 0 || r.processed === 0) break
      }
      t.ok(`ดึงโปรไฟล์เสร็จ: ${done} คน (ไม่ติดตาม ${unfollow})`)
      load()
    } catch (e) { t.err(e.message) }
    finally { setBusy(false); setTimeout(() => setProgress(null), 4000) }
  }

  const syncFollowers = async () => {
    setBusy(true)
    try {
      const r = await api.syncFollowers()
      t.ok(`followers ${r.followers} (${r.pages} หน้า)`); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <h1>ผู้ใช้ <span className="muted sm">({total.toLocaleString()})</span></h1>

      <section className="card">
        <div className="row wrap">
          <button className="primary" disabled={busy} onClick={fetchAllProfiles}>ดึงโปรไฟล์ + รูปทั้งหมด</button>
          <button disabled={busy} onClick={syncFollowers}>Sync followers (Verified OA)</button>
          {progress && (
            <span className="muted sm">
              ดึงแล้ว {progress.done.toLocaleString()} · ไม่ติดตาม {progress.unfollow} · เหลือ ~{progress.remaining.toLocaleString()}
            </span>
          )}
        </div>
        <details style={{ marginTop: 10 }}>
          <summary className="sm" style={{ cursor: 'pointer' }}>+ นำเข้า userId</summary>
          <textarea rows={3} placeholder="วาง userId คั่นด้วยขึ้นบรรทัด/comma"
                    value={importText} onChange={(e) => setImportText(e.target.value)} />
          <div className="row">
            <input placeholder="tag (ไม่บังคับ)" value={importTag} onChange={(e) => setImportTag(e.target.value)} />
            <button className="sm" disabled={busy} onClick={doImport}>นำเข้า</button>
          </div>
        </details>
      </section>

      <section className="card">
        <div className="row wrap">
          <input placeholder="ค้นหา userId / ชื่อ / note" value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && (setOffset(0), load())} />
          <select value={following} onChange={(e) => setFollowing(e.target.value)}>
            <option value="">ทั้งหมด</option>
            <option value="true">กำลังติดตาม</option>
            <option value="false">unfollow แล้ว</option>
          </select>
          <button className="sm" onClick={() => { setOffset(0); load() }}>ค้นหา</button>
        </div>

        <div className="user-grid">
          {rows.map((u) => (
            <div key={u.line_user_id} className="user-card" onClick={() => setDetailUid(u.line_user_id)}>
              <img className="user-pic" alt=""
                   src={u.picture_url || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2296%22 height=%2296%22%3E%3Crect width=%2296%22 height=%2296%22 fill=%22%23e5e7eb%22/%3E%3C/svg%3E'}
                   loading="lazy" />
              <div className="user-info">
                <div className="user-name">
                  {u.display_name || <span className="muted">(ไม่มีชื่อ)</span>}
                  {!u.is_following && <span className="chip failed">unfollow</span>}
                </div>
                <div className="muted xs ellipsis">{u.rich_menu_name || u.rich_menu_status || '–'}</div>
                <div className="muted xs mono ellipsis">{u.line_user_id}</div>
                {(u.tags || []).length > 0 && <div className="user-tags">{u.tags.map((tg) => <span key={tg} className="chip">{tg}</span>)}</div>}
              </div>
            </div>
          ))}
          {!rows.length && <p className="muted center" style={{ gridColumn: '1/-1' }}>ไม่มีข้อมูล</p>}
        </div>

        <div className="row spread">
          <button className="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>← ก่อนหน้า</button>
          <span className="muted sm">{offset + 1}–{offset + rows.length} / {total.toLocaleString()}</span>
          <button className="sm" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>ถัดไป →</button>
        </div>
      </section>

      {detailUid && (
        <UserDetail uid={detailUid} onClose={() => setDetailUid(null)} onSaved={load} />
      )}
    </div>
  )
}
