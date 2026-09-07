import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, useToast } from '../lib/ui.jsx'

const SIZES = ['Full', 'Tall', 'Compact']
const SCOPES = ['openid', 'profile', 'email', 'chat_message.write']
const EMPTY = {
  liffId: '', name: '', size: 'Full', endpointUrl: '', description: '',
  scopes: ['openid', 'profile'], botPrompt: 'normal',
  features: { ble: false, qrCode: false }, moduleMode: false, isPrimary: false, note: '',
}

function QR({ text }) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    QRCode.toDataURL(text, { width: 160, margin: 1 }).then(setSrc).catch(() => {})
  }, [text])
  return src ? <img src={src} width={140} height={140} alt="QR" style={{ borderRadius: 8, border: '1px solid var(--border)' }} /> : null
}

export default function Liff() {
  const t = useToast()
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.get('/liff').then(setData).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    setBusy(true)
    try {
      await api.post('/liff', form)
      t.ok('บันทึกแล้ว'); setForm(null); load()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const copy = (s) => { navigator.clipboard?.writeText(s); t.ok('คัดลอกแล้ว') }

  if (!data) return <Spinner />
  const env = data.env

  return (
    <div>
      <h1>LIFF Apps</h1>

      <section className="card">
        <h3>ค่าที่ระบบใช้อยู่ (จาก Environment)</h3>
        <table className="kv">
          <tbody>
            <tr><th>VITE_LIFF_ID</th><td className="mono">{env.VITE_LIFF_ID || '–'} {env.VITE_LIFF_ID && <button className="xs" onClick={() => copy(env.VITE_LIFF_ID)}>คัดลอก</button>}</td></tr>
            <tr><th>LIFF_CHANNEL_ID</th><td className="mono">{env.LIFF_CHANNEL_ID || '–'}</td></tr>
            <tr><th>Endpoint ที่แนะนำ</th><td className="mono">{env.recommendedEndpoint} <button className="xs" onClick={() => copy(env.recommendedEndpoint)}>คัดลอก</button></td></tr>
          </tbody>
        </table>
        <p className="muted xs">
          {data.syncEnabled
            ? (data.syncError ? `sync จาก LINE ล้มเหลว: ${data.syncError}` : 'ดึงรายการจาก LINE อัตโนมัติ ✓')
            : 'ยังไม่ได้ตั้ง LINE_LOGIN_CHANNEL_TOKEN — เพิ่มรายการ LIFF เอง (ดูรายละเอียดครบจาก LINE Developers Console)'}
        </p>
      </section>

      <div className="row spread">
        <h3 style={{ margin: 0 }}>รายการ LIFF ({data.apps.length})</h3>
        <button className="sm primary" onClick={() => setForm({ ...EMPTY, liffId: env.VITE_LIFF_ID?.includes('-') ? '' : '', endpointUrl: env.recommendedEndpoint })}>+ เพิ่ม LIFF</button>
      </div>

      {data.apps.length === 0 && <p className="muted card center">ยังไม่มี — กด "เพิ่ม LIFF"</p>}

      {data.apps.map((a) => {
        const L = a.line || {}
        return (
          <section className="card" key={a.liffId}>
            <div className="row spread wrap">
              <div>
                <h3 style={{ margin: 0 }}>
                  {a.name || a.description || L.description || '(ไม่มีชื่อ)'}
                  {a.is_primary && <span className="chip ok" style={{ marginLeft: 6 }}>หลัก</span>}
                  <span className="chip" style={{ marginLeft: 4 }}>{a.source === 'line' ? 'จาก LINE' : 'บันทึกเอง'}</span>
                </h3>
                <code className="xs">{a.liffId}</code>
              </div>
              <div className="row">
                <button className="xs" onClick={() => window.open(a.permanentLink, '_blank')}>เปิด</button>
                <button className="xs" onClick={() => setForm({
                  ...EMPTY, ...a, liffId: a.liffId, endpointUrl: a.endpoint_url || L.view?.url || '',
                  name: a.name || a.description || L.description || '', size: a.size || L.view?.type || 'Full',
                  scopes: a.scopes?.length ? a.scopes : (L.scope || ['openid', 'profile']),
                  botPrompt: a.bot_prompt || L.botPrompt || 'normal',
                  features: { ...(a.features || {}), ...(L.features || {}) },
                  moduleMode: a.module_mode ?? (L.view?.moduleMode || false),
                  isPrimary: a.is_primary || false, note: a.note || '',
                })}>แก้ไข</button>
                <button className="xs danger" onClick={() => confirm('ลบรายการนี้? (ไม่ลบใน LINE)') && api.del(`/liff/${a.liffId}`).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
              </div>
            </div>

            <div className="liff-grid">
              <table className="kv">
                <tbody>
                  <tr><th>Channel ID</th><td className="mono">{a.channelId}</td></tr>
                  <tr><th>ขนาดหน้าจอ</th><td>{a.size || L.view?.type || '–'}</td></tr>
                  <tr><th>Endpoint URL</th><td className="mono xs">{a.endpoint_url || L.view?.url || '–'}</td></tr>
                  <tr><th>Scopes</th><td>{(a.scopes?.length ? a.scopes : L.scope || []).map((s) => <span key={s} className="chip" style={{ marginRight: 3 }}>{s}</span>) || '–'}</td></tr>
                  <tr><th>Bot link</th><td>{a.bot_prompt || L.botPrompt || '–'}</td></tr>
                  <tr><th>Scan QR</th><td>{(a.features?.qrCode ?? L.features?.qrCode) ? 'เปิด' : 'ปิด'}</td></tr>
                  <tr><th>BLE</th><td>{(a.features?.ble ?? L.features?.ble) ? 'เปิด' : 'ปิด'}</td></tr>
                  <tr><th>Module mode</th><td>{(a.module_mode ?? L.view?.moduleMode) ? 'เปิด' : 'ปิด'}</td></tr>
                  <tr><th>Permanent link</th><td className="mono xs">{a.permanentLink} <button className="xs" onClick={() => copy(a.permanentLink)}>คัดลอก</button></td></tr>
                  <tr><th>line:// link</th><td className="mono xs">{a.shortLink}</td></tr>
                  {a.note && <tr><th>Note</th><td>{a.note}</td></tr>}
                  {a.consoleUrl && <tr><th>Console</th><td><a href={a.consoleUrl} target="_blank" rel="noreferrer">เปิดใน LINE Developers ↗</a></td></tr>}
                </tbody>
              </table>
              <div style={{ textAlign: 'center' }}>
                <QR text={a.permanentLink} />
                <div className="muted xs">สแกนเพื่อเปิด</div>
              </div>
            </div>
          </section>
        )
      })}

      {form && (
        <div className="modal-bg" onClick={() => setForm(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>{form.liff_id || data.apps.find((x) => x.liffId === form.liffId) ? 'แก้ไข LIFF' : 'เพิ่ม LIFF'}</h3><button className="xs" onClick={() => setForm(null)}>✕</button></div>

            <label className="sm">LIFF ID *</label>
            <input placeholder="2009830584-xxxxxxxx" value={form.liffId}
                   onChange={(e) => setForm({ ...form, liffId: e.target.value.trim() })} className="mono" />
            <label className="sm">ชื่อ (สำหรับจำ)</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <label className="sm">Endpoint URL</label>
            <input placeholder="https://…" value={form.endpointUrl} onChange={(e) => setForm({ ...form, endpointUrl: e.target.value })} />
            <div className="row wrap">
              <label>ขนาด&nbsp;
                <select value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}>
                  {SIZES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </label>
              <label>Bot link&nbsp;
                <select value={form.botPrompt} onChange={(e) => setForm({ ...form, botPrompt: e.target.value })}>
                  <option value="normal">normal</option><option value="aggressive">aggressive</option><option value="none">none</option>
                </select>
              </label>
            </div>
            <label className="sm">Scopes</label>
            <div className="row wrap">
              {SCOPES.map((s) => (
                <label key={s}><input type="checkbox" checked={form.scopes.includes(s)}
                  onChange={(e) => setForm({ ...form, scopes: e.target.checked ? [...form.scopes, s] : form.scopes.filter((x) => x !== s) })} /> {s}</label>
              ))}
            </div>
            <div className="row wrap">
              <label><input type="checkbox" checked={form.features.qrCode} onChange={(e) => setForm({ ...form, features: { ...form.features, qrCode: e.target.checked } })} /> Scan QR</label>
              <label><input type="checkbox" checked={form.features.ble} onChange={(e) => setForm({ ...form, features: { ...form.features, ble: e.target.checked } })} /> BLE</label>
              <label><input type="checkbox" checked={form.moduleMode} onChange={(e) => setForm({ ...form, moduleMode: e.target.checked })} /> Module mode</label>
              <label><input type="checkbox" checked={form.isPrimary} onChange={(e) => setForm({ ...form, isPrimary: e.target.checked })} /> ตั้งเป็นหลัก</label>
            </div>
            <label className="sm">Note</label>
            <textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            <button className="primary" onClick={save} disabled={busy}>{busy && <InlineSpinner />}บันทึก</button>
          </div>
        </div>
      )}
    </div>
  )
}
