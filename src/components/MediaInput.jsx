import { useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, InlineSpinner } from '../lib/ui.jsx'

// ช่องกรอก URL รูป/วิดีโอ + ปุ่มอัปโหลดขึ้น Supabase Storage
export default function MediaInput({ value, onChange, placeholder = 'https:// หรือกดอัปโหลด', accept = 'image/*', preview = true }) {
  const t = useToast()
  const ref = useRef(null)
  const [busy, setBusy] = useState(false)

  const pick = async (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    setBusy(true)
    try {
      const dataUrl = await new Promise((res, rej) => {
        const r = new FileReader()
        r.onload = () => res(r.result); r.onerror = rej
        r.readAsDataURL(f)
      })
      const r = await api.post('/upload', { dataUrl })
      onChange(r.url)
      t.ok(`อัปโหลดแล้ว (${Math.round(r.size / 1024)} KB)`)
    } catch (err) { t.err(err.message) }
    finally { setBusy(false); if (ref.current) ref.current.value = '' }
  }

  return (
    <div className="media-input">
      <div className="row" style={{ gap: 6 }}>
        <input style={{ flex: 1 }} placeholder={placeholder} value={value || ''} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="sm" onClick={() => ref.current?.click()} disabled={busy}>
          {busy ? <InlineSpinner /> : '📎'} อัปโหลด
        </button>
        <input ref={ref} type="file" accept={accept} hidden onChange={pick} />
      </div>
      {preview && value && /^https?:/.test(value) && (
        <img className="media-thumb" src={value} alt="" onError={(e) => { e.target.style.display = 'none' }} />
      )}
    </div>
  )
}
