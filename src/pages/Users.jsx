import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { getIdToken } from '../lib/auth.js'
import { useToast, SkeletonCards, InlineSpinner } from '../lib/ui.jsx'
import { useProgress } from '../lib/progress.jsx'
import UserDetail from '../components/UserDetail.jsx'
import ImportMapper from '../components/ImportMapper.jsx'

export default function Users() {
  const t = useToast()
  const prog = useProgress()
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [following, setFollowing] = useState('')
  const [tag, setTag] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [detailUid, setDetailUid] = useState(null)
  const [sel, setSel] = useState(() => new Set())
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [importTag, setImportTag] = useState('')
  const [tagInput, setTagInput] = useState('')
  const limit = 60

  const load = () => {
    setBusy(true)
    api.users({ q, following, tag, limit, offset })
      .then((d) => { setRows(d.users); setTotal(d.total) })
      .catch((e) => t.err(e.message))
      .finally(() => setBusy(false))
  }
  useEffect(() => { load() }, [offset, following, tag]) // eslint-disable-line

  const toggle = (uid) => setSel((s) => {
    const n = new Set(s); n.has(uid) ? n.delete(uid) : n.add(uid); return n
  })
  const allSel = rows.length > 0 && rows.every((r) => sel.has(r.line_user_id))
  const toggleAll = () => setSel((s) => allSel ? new Set() : new Set(rows.map((r) => r.line_user_id)))

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

  const bulkTag = async (mode) => {
    if (!sel.size) return
    const tags = tagInput.split(',').map((s) => s.trim()).filter(Boolean)
    if (!tags.length) return t.err('พิมพ์ tag ก่อน')
    setBusy(true)
    try {
      const r = await api.bulkTag({ userIds: [...sel], [mode]: tags })
      t.ok(`${mode === 'add' ? 'ใส่' : 'ลบ'} tag: เปลี่ยน ${r.changed} คน`)
      setTagInput(''); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const exportCsv = () => {
    const url = api.exportUsersUrl({ following, tag })
    fetch(url, { headers: { Authorization: `Bearer ${getIdToken() || ''}` } })
      .then((r) => r.blob())
      .then((b) => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(b); a.download = `users-${new Date().toISOString().slice(0, 10)}.csv`; a.click()
        URL.revokeObjectURL(a.href)
      })
      .catch(() => t.err('export ล้มเหลว'))
  }

  const fetchAllProfiles = async () => {
    setBusy(true)
    const task = prog.start('กำลังดึงโปรไฟล์ + รูป', 0)
    let done = 0, unfollow = 0, tot = 0
    try {
      for (let i = 0; i < 80; i++) {
        const r = await api.refreshProfiles({ target: 'missing', limit: 400 })
        done += r.profiles_fetched; unfollow += r.not_following
        if (tot === 0) tot = r.processed + r.remaining
        task.setTotal(tot)
        task.set(done + unfollow, `ดึงได้ ${done.toLocaleString()} · ไม่ติดตาม ${unfollow}`)
        if (r.remaining === 0 || r.processed === 0) break
      }
      t.ok(`ดึงโปรไฟล์เสร็จ: ${done.toLocaleString()} คน`)
      load()
    } catch (e) { t.err(e.message) }
    finally { task.done(); setBusy(false) }
  }

  return (
    <div>
      <h1>ผู้ใช้ <span className="muted sm">({total.toLocaleString()})</span></h1>

      <section className="card">
        <div className="row wrap">
          <button className="primary sm" disabled={busy} onClick={fetchAllProfiles}>ดึงโปรไฟล์ + รูป</button>
          <button className="sm" disabled={busy} onClick={() => api.syncFollowers().then((r) => { t.ok(`followers ${r.followers}`); load() }).catch((e) => t.err(e.message))}>Sync followers</button>
          <button className="sm" onClick={() => setImportOpen(true)}>นำเข้าจาก CSV (map คอลัมน์)</button>
          <button className="sm" onClick={exportCsv}>⬇ Export CSV</button>
        </div>
        <details style={{ marginTop: 8 }}>
          <summary className="sm" style={{ cursor: 'pointer' }}>+ วาง userId เร็ว ๆ</summary>
          <textarea rows={3} placeholder="วาง userId คั่นด้วยขึ้นบรรทัด/comma"
                    value={importText} onChange={(e) => setImportText(e.target.value)} />
          <div className="row">
            <input placeholder="tag" value={importTag} onChange={(e) => setImportTag(e.target.value)} />
            <button className="sm" disabled={busy} onClick={doImport}>นำเข้า</button>
          </div>
        </details>
      </section>

      <section className="card">
        <div className="row wrap">
          <input placeholder="ค้นหา userId / ชื่อ / note" value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && (setOffset(0), load())} />
          <select value={following} onChange={(e) => setFollowing(e.target.value)}>
            <option value="">ทุกสถานะ</option>
            <option value="true">กำลังติดตาม</option>
            <option value="false">unfollow</option>
          </select>
          <input placeholder="กรอง tag" value={tag} onChange={(e) => setTag(e.target.value)} style={{ width: 110 }} />
          <button className="sm" onClick={() => { setOffset(0); load() }}>ค้นหา</button>
        </div>

        {/* bulk bar */}
        <div className="row wrap bulkbar">
          <label className="sm"><input type="checkbox" checked={allSel} onChange={toggleAll} /> เลือกหน้านี้</label>
          <span className="muted sm">เลือก {sel.size}</span>
          <input placeholder="tag (คั่น ,)" value={tagInput} onChange={(e) => setTagInput(e.target.value)} style={{ width: 130 }} />
          <button className="xs" disabled={!sel.size || busy} onClick={() => bulkTag('add')}>+ ใส่ tag</button>
          <button className="xs" disabled={!sel.size || busy} onClick={() => bulkTag('remove')}>− ลบ tag</button>
          {sel.size > 0 && <button className="xs" onClick={() => setSel(new Set())}>ล้างที่เลือก</button>}
        </div>

        {busy && !rows.length && <SkeletonCards count={12} />}

        <div className="user-grid" hidden={busy && !rows.length}>
          {rows.map((u) => (
            <div key={u.line_user_id} className={`user-card ${sel.has(u.line_user_id) ? 'sel' : ''}`}>
              <input type="checkbox" className="user-cb" checked={sel.has(u.line_user_id)}
                     onChange={() => toggle(u.line_user_id)} onClick={(e) => e.stopPropagation()} />
              <img className="user-pic" alt="" onClick={() => setDetailUid(u.line_user_id)}
                   src={u.picture_url || FALLBACK} loading="lazy" />
              <div className="user-info" onClick={() => setDetailUid(u.line_user_id)}>
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
          {!rows.length && !busy && <p className="muted center" style={{ gridColumn: '1/-1' }}>ไม่มีข้อมูล</p>}
        </div>

        <div className="row spread">
          <button className="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>← ก่อนหน้า</button>
          <span className="muted sm">{offset + 1}–{offset + rows.length} / {total.toLocaleString()}</span>
          <button className="sm" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>ถัดไป →</button>
        </div>
      </section>

      {detailUid && <UserDetail uid={detailUid} onClose={() => setDetailUid(null)} onSaved={load} />}
      {importOpen && <ImportMapper onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); load() }} />}
    </div>
  )
}

const FALLBACK = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2296%22 height=%2296%22%3E%3Crect width=%2296%22 height=%2296%22 fill=%22%23e5e7eb%22/%3E%3C/svg%3E'
