import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { SkeletonRows, InlineSpinner, useToast } from '../lib/ui.jsx'

export default function Admins({ me }) {
  const t = useToast()
  const [rows, setRows] = useState(null)
  const [uid, setUid] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('admin')
  const [health, setHealth] = useState(null)
  const [backups, setBackups] = useState([])
  const [fields, setFields] = useState([])
  const [nf, setNf] = useState({ key: '', label: '', type: 'text', options: '' })
  const [settings, setSettings] = useState({})
  const [busy, setBusy] = useState('')

  const load = () => api.admins().then((d) => setRows(d.admins)).catch((e) => t.err(e.message))
  const loadSys = () => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }))
    api.backupList().then((d) => setBackups(d.backups)).catch(() => {})
    api.fields().then((d) => setFields(d.fields)).catch(() => {})
    api.settings().then((d) => setSettings(d.settings)).catch(() => {})
  }
  const toggleSetting = async (key, val) => {
    setSettings((s) => ({ ...s, [key]: val }))
    try { await api.setSetting(key, val) } catch (e) { t.err(e.message) }
  }
  const addField = async () => {
    try {
      await api.saveField({ ...nf, options: nf.options.split(',').map((s) => s.trim()).filter(Boolean) })
      t.ok('เพิ่ม field แล้ว'); setNf({ key: '', label: '', type: 'text', options: '' }); loadSys()
    } catch (e) { t.err(e.message) }
  }
  useEffect(() => { load(); loadSys() }, [])

  const add = async () => {
    if (!uid.startsWith('U')) return t.err('userId ต้องขึ้นต้น U')
    try {
      await api.addAdmin({ lineUserId: uid.trim(), name, role })
      t.ok('เพิ่มแล้ว'); setUid(''); setName(''); load()
    } catch (e) { t.err(e.message) }
  }

  const backupNow = async () => {
    setBusy('backup')
    try { const r = await api.backupNow(); t.ok(`สำรองแล้ว ${r.size_kb} KB`); loadSys() }
    catch (e) { t.err(e.message) } finally { setBusy('') }
  }

  const downloadBackup = async (b) => {
    setBusy('dl' + b.id)
    try {
      const full = await api.backupGet(b.id)
      const blob = new Blob([JSON.stringify(full.tables, null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob); a.download = `backup-${b.day}.json`; a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { t.err(e.message) } finally { setBusy('') }
  }

  if (!rows) return <SkeletonRows rows={5} cols={4} />
  const canEdit = ['owner', 'admin'].includes(me.role)
  const c = health?.checks || {}

  return (
    <div>
      <h1>ผู้ดูแล & ระบบ</h1>

      <section className="card">
        <h3>สถานะระบบ {health && <span className={`chip ${health.ok ? 'ok' : 'failed'}`}>{health.ok ? 'ปกติ' : 'มีปัญหา'}</span>}</h3>
        {!health ? <SkeletonRows rows={3} cols={2} /> : (
          <table className="kv">
            <tbody>
              <tr><th>ฐานข้อมูล</th><td>{c.db === 'ok' ? '✅ เชื่อมต่อได้' : `❌ ${c.db}`}</td></tr>
              <tr><th>โควตาข้อความ</th><td>{typeof c.line_quota === 'object' ? JSON.stringify(c.line_quota) : (c.line_quota ?? '–')} {c.line_usage != null && `· ใช้ ${c.line_usage.toLocaleString()}`}</td></tr>
              <tr><th>Env</th><td>
                {Object.entries(c.env || {}).map(([k, v]) => (
                  <span key={k} className={`chip ${v ? 'ok' : 'failed'}`} style={{ marginRight: 4 }}>{k}{v ? '' : ' ✗'}</span>
                ))}
              </td></tr>
              <tr><th>Cron ล่าสุด</th><td className="xs muted">
                {(c.last_cron || []).slice(0, 3).map((x, i) => <div key={i}>{x.action} · {new Date(x.created_at).toLocaleString('th-TH')}</div>)}
                {!(c.last_cron || []).length && 'ยังไม่มี'}
              </td></tr>
            </tbody>
          </table>
        )}
        <button className="sm" onClick={loadSys} style={{ marginTop: 8 }}>เช็คใหม่</button>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>สำรองข้อมูล</h3>
          <button className="sm primary" onClick={backupNow} disabled={busy === 'backup'}>
            {busy === 'backup' && <InlineSpinner />}สำรองเดี๋ยวนี้
          </button>
        </div>
        <p className="muted xs">สำรองอัตโนมัติทุกวัน + Supabase มี backup รายวันของตัวเองด้วย (7 วัน) · เก็บในระบบ 21 วันล่าสุด</p>
        <table>
          <thead><tr><th>วันที่</th><th>ขนาด</th><th>เมื่อ</th><th></th></tr></thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.id}>
                <td>{b.day}</td>
                <td>{b.size_kb} KB</td>
                <td className="muted xs">{new Date(b.created_at).toLocaleString('th-TH')}</td>
                <td><button className="xs" onClick={() => downloadBackup(b)} disabled={busy === 'dl' + b.id}>
                  {busy === 'dl' + b.id && <InlineSpinner />}ดาวน์โหลด JSON
                </button></td>
              </tr>
            ))}
            {!backups.length && <tr><td colSpan={4} className="muted center">ยังไม่มี — กด "สำรองเดี๋ยวนี้"</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>การแจ้งเตือน</h3>
        <label className="row">
          <input type="checkbox" checked={settings.slip_notify_all_images !== false}
                 onChange={(e) => toggleSetting('slip_notify_all_images', e.target.checked)} />
          แจ้งแอดมิน (เข้า LINE) ทุกครั้งที่มีรูป/สลิปเข้ามา
        </label>
        <p className="muted xs">ถ้าปิด จะแจ้งเฉพาะรูปที่ส่งหลังคุยเรื่องชำระเงิน/สมัคร · ต้องตั้ง ALERT_USER_IDS · ตรวจสลิปอัตโนมัติ (ยอด/ธนาคาร) ต้องตั้ง env EASYSLIP_TOKEN</p>
      </section>

      <section className="card">
        <h3>ฟิลด์ข้อมูลเพิ่มเติมของผู้ใช้ (Custom fields)</h3>
        <table>
          <thead><tr><th>key</th><th>ชื่อ</th><th>ชนิด</th><th>ตัวเลือก</th><th></th></tr></thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.key}>
                <td className="mono xs">{f.key}</td><td>{f.label}</td><td>{f.type}</td>
                <td className="muted xs">{(f.options || []).join(', ')}</td>
                <td><button className="xs danger" onClick={() => confirm('ลบ field?') && api.delField(f.key).then(loadSys)}>ลบ</button></td>
              </tr>
            ))}
            {!fields.length && <tr><td colSpan={5} className="muted center">ยังไม่มี — เช่น คอร์ส, รุ่น, วันหมดอายุ</td></tr>}
          </tbody>
        </table>
        <div className="row wrap" style={{ marginTop: 8 }}>
          <input placeholder="key (a-z_)" value={nf.key} onChange={(e) => setNf({ ...nf, key: e.target.value })} style={{ width: 110 }} />
          <input placeholder="ชื่อที่แสดง" value={nf.label} onChange={(e) => setNf({ ...nf, label: e.target.value })} style={{ width: 130 }} />
          <select value={nf.type} onChange={(e) => setNf({ ...nf, type: e.target.value })}>
            <option value="text">ข้อความ</option><option value="number">ตัวเลข</option>
            <option value="date">วันที่</option><option value="select">ตัวเลือก</option>
          </select>
          {nf.type === 'select' && <input placeholder="ตัวเลือก คั่น ," value={nf.options} onChange={(e) => setNf({ ...nf, options: e.target.value })} style={{ width: 150 }} />}
          <button className="primary sm" onClick={addField}>เพิ่ม</button>
        </div>
      </section>

      <section className="card">
        <h3>ผู้ดูแล ({rows.length})</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>userId</th><th>ชื่อ</th><th>role</th><th>เพิ่มเมื่อ</th><th></th></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.line_user_id}>
                  <td className="mono xs">{a.line_user_id}</td>
                  <td>{a.name}</td>
                  <td><span className="chip">{a.role}</span></td>
                  <td className="muted xs">{new Date(a.added_at).toLocaleDateString('th-TH')}</td>
                  <td>
                    {me.role === 'owner' && a.line_user_id !== me.userId && (
                      <button className="xs danger" onClick={() => confirm('ลบผู้ดูแลนี้?') && api.delAdmin(a.line_user_id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {canEdit && (
        <section className="card">
          <h3>เพิ่มผู้ดูแล</h3>
          <div className="row wrap">
            <input placeholder="LINE userId (U...)" value={uid} onChange={(e) => setUid(e.target.value)} />
            <input placeholder="ชื่อ" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="admin">admin</option>
              <option value="viewer">viewer</option>
              <option value="owner">owner</option>
            </select>
            <button className="primary" onClick={add}>เพิ่ม</button>
          </div>
        </section>
      )}
    </div>
  )
}
