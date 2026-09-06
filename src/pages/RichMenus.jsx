import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, useToast } from '../lib/ui.jsx'
import RichMenuBuilder from '../components/RichMenuBuilder.jsx'

export default function RichMenus() {
  const t = useToast()
  const [data, setData] = useState(null)
  const [usage, setUsage] = useState({})
  const [building, setBuilding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState('')
  const [target, setTarget] = useState('all')
  const [userIds, setUserIds] = useState('')
  const [setDefault, setSetDefault] = useState(true)

  const load = () => {
    api.richmenus().then(setData).catch((e) => t.err(e.message))
    api.richmenuUsage()
      .then((d) => setUsage(Object.fromEntries(d.items.map((i) => [i.richMenuId || '__none__', i.count]))))
      .catch(() => {})
  }
  useEffect(() => { load() }, [])

  if (!data) return <Spinner />
  const { defaultRichMenuId, aliases } = data
  const menus = [...data.menus].sort((a, b) => (usage[b.richMenuId] || 0) - (usage[a.richMenuId] || 0))

  const parseIds = () =>
    userIds.split(/[\s,]+/).map((s) => s.trim()).filter((s) => s.startsWith('U'))

  const run = async (mode) => {
    if (mode === 'link' && !sel) return t.err('เลือก rich menu ก่อน')
    const payload = { mode, target, richMenuId: sel, setDefault }
    if (target === 'list') payload.userIds = parseIds()
    const label = target === 'all' ? 'ผู้ใช้ทุกคน' : target === 'none' ? 'คนที่ยังไม่มีเมนู' :
      target === 'list' ? `${parseIds().length} คนในลิสต์` : `tag`
    if (!confirm(`${mode === 'link' ? 'ผูก' : 'ถอด'} rich menu กับ ${label}?`)) return
    setBusy(true)
    try {
      const r = await api.assignMenu(payload)
      t.ok(`เสร็จ: สำเร็จ ${r.ok} / ล้มเหลว ${r.fail} (จาก ${r.total})`)
      load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const sync = async () => {
    setBusy(true)
    try {
      const r = await api.syncMenu({ target: 'all' })
      t.ok(`sync: assigned ${r.assigned} / none ${r.none} / error ${r.error}`)
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <h1>Rich Menu</h1>

      <section className="card">
        <div className="row spread">
          <h3>รายการเมนู ({menus.length})</h3>
          <div className="row">
            <button className="sm primary" onClick={() => setBuilding(true)}>+ สร้างเมนูใหม่</button>
            <button className="sm" onClick={sync} disabled={busy}>Sync สถานะผู้ใช้ทั้งหมด</button>
          </div>
        </div>
        <table>
          <thead><tr><th></th><th>ชื่อ</th><th>ใช้อยู่</th><th>chatBar</th><th>ขนาด</th><th>richMenuId</th><th></th></tr></thead>
          <tbody>
            {menus.map((m) => (
              <tr key={m.richMenuId} className={sel === m.richMenuId ? 'selected' : ''}>
                <td><input type="radio" checked={sel === m.richMenuId}
                           onChange={() => setSel(m.richMenuId)} /></td>
                <td>{m.name} {m.richMenuId === defaultRichMenuId && <span className="chip ok">default</span>}</td>
                <td><b>{(usage[m.richMenuId] || 0).toLocaleString()}</b></td>
                <td>{m.chatBarText}</td>
                <td className="muted sm">{m.size?.width}×{m.size?.height}</td>
                <td className="mono xs">{m.richMenuId}</td>
                <td className="row">
                  <button className="xs" onClick={() => api.setDefaultMenu(m.richMenuId).then(() => { t.ok('ตั้ง default'); load() }).catch((e) => t.err(e.message))}>
                    ตั้ง default
                  </button>
                  <button className="xs danger" onClick={() => confirm('ลบเมนูนี้?') && api.deleteMenu(m.richMenuId).then(() => { t.ok('ลบแล้ว'); load() }).catch((e) => t.err(e.message))}>
                    ลบ
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {defaultRichMenuId && (
          <p className="muted sm">
            default ปัจจุบัน: <code>{defaultRichMenuId}</code>{' '}
            <button className="xs" onClick={() => api.clearDefaultMenu().then(() => { t.ok('ล้าง default'); load() })}>ล้าง</button>
          </p>
        )}
        {!!aliases.length && (
          <p className="muted sm">alias: {aliases.map((a) => `${a.richMenuAliasId}→${a.richMenuId.slice(-6)}`).join(' , ')}</p>
        )}
      </section>

      <section className="card">
        <h3>ผูก / ถอด เป็นชุด</h3>
        <div className="row wrap">
          <label>ปลายทาง:&nbsp;
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="all">ผู้ใช้ที่ติดตามทุกคน</option>
              <option value="none">เฉพาะคนที่ยังไม่มีเมนู</option>
              <option value="list">ระบุ userId เอง</option>
            </select>
          </label>
          <label><input type="checkbox" checked={setDefault} onChange={(e) => setSetDefault(e.target.checked)} /> ตั้งเป็น default ด้วย</label>
        </div>
        {target === 'list' && (
          <textarea rows={5} placeholder="วาง userId (คั่นด้วยขึ้นบรรทัด/comma)"
                    value={userIds} onChange={(e) => setUserIds(e.target.value)} />
        )}
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => run('link')}>
            ผูกเมนูที่เลือก {sel && `(${menus.find((m) => m.richMenuId === sel)?.name})`}
          </button>
          <button disabled={busy} onClick={() => run('unlink')}>ถอดเมนู</button>
        </div>
      </section>

      {building && <RichMenuBuilder onCancel={() => setBuilding(false)} onDone={() => { setBuilding(false); load() }} />}
    </div>
  )
}
