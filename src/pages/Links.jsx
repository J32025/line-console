import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '../lib/api.js'
import { SkeletonRows, InlineSpinner, useToast } from '../lib/ui.jsx'

export default function Links() {
  const t = useToast()
  const [links, setLinks] = useState(null)
  const [target, setTarget] = useState('')
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [stats, setStats] = useState(null)   // {code, data}

  const load = () => api.links().then((d) => setLinks(d.links)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const create = async () => {
    if (!/^https?:\/\//.test(target)) return t.err('ใส่ URL ปลายทาง')
    setBusy(true)
    try {
      const r = await api.createLink({ target, label })
      t.ok('สร้างแล้ว'); navigator.clipboard?.writeText(r.shortUrl)
      setTarget(''); setLabel(''); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const showStats = async (code) => {
    setStats({ code, data: null })
    try { setStats({ code, data: await api.linkStats(code) }) }
    catch (e) { t.err(e.message) }
  }

  if (!links) return <SkeletonRows rows={5} cols={4} />

  return (
    <div>
      <h1>ลิงก์ติดตามคลิก</h1>

      <section className="card">
        <h3>สร้างลิงก์สั้น</h3>
        <input placeholder="URL ปลายทาง เช่น https://forms.gle/xxx" value={target} onChange={(e) => setTarget(e.target.value)} />
        <div className="row">
          <input placeholder="ชื่อ (สำหรับจำ)" value={label} onChange={(e) => setLabel(e.target.value)} />
          <button className="primary sm" onClick={create} disabled={busy}>{busy && <InlineSpinner />}สร้าง + คัดลอก</button>
        </div>
        <p className="muted xs">เอาลิงก์สั้น (เช่น <code>…/r/ab12cd</code>) ไปใส่ในข้อความ/broadcast — ทุกครั้งที่มีคนกด ระบบนับคลิกให้</p>
      </section>

      <section className="card">
        <h3>ลิงก์ทั้งหมด ({links.length})</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>ชื่อ</th><th>ลิงก์สั้น</th><th>ปลายทาง</th><th>คลิก</th><th></th></tr></thead>
            <tbody>
              {links.map((l) => (
                <tr key={l.code}>
                  <td>{l.label || <span className="muted">—</span>}</td>
                  <td><code className="xs">/r/{l.code}</code> <button className="xs" onClick={() => { navigator.clipboard?.writeText(`${location.origin}/r/${l.code}`); t.ok('คัดลอก') }}>คัดลอก</button></td>
                  <td className="muted xs ellipsis" style={{ maxWidth: 200 }}>{l.target}</td>
                  <td><b>{l.clicks}</b></td>
                  <td className="row">
                    <button className="xs" onClick={() => showStats(l.code)}>กราฟ</button>
                    <button className="xs danger" onClick={() => confirm('ลบลิงก์?') && api.delLink(l.code).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                  </td>
                </tr>
              ))}
              {!links.length && <tr><td colSpan={5} className="muted center">ยังไม่มีลิงก์</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {stats && (
        <div className="modal-bg" onClick={() => setStats(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>สถิติ /r/{stats.code}</h3><button className="xs" onClick={() => setStats(null)}>✕</button></div>
            {!stats.data ? <SkeletonRows rows={3} cols={2} /> : (
              <>
                <div className="stat">
                  <div><b>{stats.data.total}</b><span className="muted"> คลิกรวม</span></div>
                  <div><b>{stats.data.unique_users}</b><span className="muted"> user (ที่ระบุตัวได้)</span></div>
                </div>
                {stats.data.by_day.length > 0 && (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={stats.data.by_day}>
                      <XAxis dataKey="day" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 11 }} /><Tooltip />
                      <Bar dataKey="clicks" fill="#06c755" />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
