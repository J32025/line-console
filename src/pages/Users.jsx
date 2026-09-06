import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../lib/ui.jsx'

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
  const limit = 100

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
      t.ok(`import: ใหม่ ${r.new} / ซ้ำ ${r.duplicate} (ส่งมา ${r.submitted})`)
      setImportText('')
      load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const refreshProfiles = async () => {
    setBusy(true)
    try {
      const r = await api.refreshProfiles({ target: 'missing', limit: 500 })
      t.ok(`ดึงโปรไฟล์ ${r.profiles_fetched}/${r.total}`)
      load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const syncFollowers = async () => {
    setBusy(true)
    try {
      const r = await api.syncFollowers()
      t.ok(`followers ${r.followers} (${r.pages} หน้า)`)
      load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <h1>ผู้ใช้ <span className="muted sm">({total.toLocaleString()})</span></h1>

      <section className="card">
        <h3>นำเข้า userId</h3>
        <textarea rows={4} placeholder="วาง userId คั่นด้วยขึ้นบรรทัด/comma"
                  value={importText} onChange={(e) => setImportText(e.target.value)} />
        <div className="row">
          <input placeholder="tag (ไม่บังคับ)" value={importTag} onChange={(e) => setImportTag(e.target.value)} />
          <button className="primary" disabled={busy} onClick={doImport}>นำเข้า</button>
          <button disabled={busy} onClick={refreshProfiles}>ดึงโปรไฟล์ที่ยังไม่มี</button>
          <button disabled={busy} onClick={syncFollowers}>Sync followers (Verified OA)</button>
        </div>
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
        <div className="table-scroll">
          <table>
            <thead><tr><th>ผู้ใช้</th><th>userId</th><th>Rich Menu</th><th>ที่มา</th><th>tags</th><th>อัปเดต</th></tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.line_user_id}>
                  <td className="row">
                    {u.picture_url && <img className="avatar sm" src={u.picture_url} alt="" />}
                    {u.display_name || <span className="muted">–</span>}
                    {!u.is_following && <span className="chip failed">unfollow</span>}
                  </td>
                  <td className="mono xs">{u.line_user_id}</td>
                  <td>{u.rich_menu_name || <span className="muted">{u.rich_menu_status || '–'}</span>}</td>
                  <td className="muted sm">{u.source}</td>
                  <td className="muted xs">{(u.tags || []).join(', ')}</td>
                  <td className="muted xs">{u.updated_at ? new Date(u.updated_at).toLocaleDateString('th-TH') : '–'}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={6} className="muted center">ไม่มีข้อมูล</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="row spread">
          <button className="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>← ก่อนหน้า</button>
          <span className="muted sm">{offset + 1}–{offset + rows.length} / {total.toLocaleString()}</span>
          <button className="sm" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>ถัดไป →</button>
        </div>
      </section>
    </div>
  )
}
