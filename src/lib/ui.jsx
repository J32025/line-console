import { createContext, useContext, useState, useCallback } from 'react'

const ToastCtx = createContext(null)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = useCallback((msg, type = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, msg, type }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === 'error' ? 6000 : 3000)
  }, [])
  return (
    <ToastCtx.Provider value={{ ok: (m) => push(m, 'ok'), err: (m) => push(m, 'error'), info: push }}>
      {children}
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>{t.msg}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

/* ---------- loading indicators ---------- */

// สปินเนอร์เล็ก ๆ ใส่ในปุ่ม / บรรทัด
export function InlineSpinner() {
  return <span className="spinner spinner-xs" aria-hidden />
}

// โหลดทั้งหน้า — สปินเนอร์ + ข้อความกะพริบ
export function Spinner({ label = 'กำลังโหลด…' }) {
  return (
    <div className="loading-page" role="status" aria-live="polite">
      <span className="spinner spinner-lg" />
      <span className="loading-text">{label}</span>
    </div>
  )
}

// โครงร่างเทา ๆ (shimmer) — ใช้ตอนโหลด list/table
export function Skeleton({ w = '100%', h = 14, r = 6, style }) {
  return <span className="skeleton" style={{ width: w, height: h, borderRadius: r, ...style }} />
}

export function SkeletonRows({ rows = 6, cols = 4 }) {
  return (
    <div className="skel-table" role="status" aria-label="กำลังโหลด">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skel-row" key={i}>
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} w={j === 0 ? '40%' : '70%'} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonCards({ count = 6 }) {
  return (
    <div className="skel-cards" role="status" aria-label="กำลังโหลด">
      {Array.from({ length: count }).map((_, i) => (
        <div className="skel-card" key={i}>
          <Skeleton w={44} h={44} r={10} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Skeleton w="55%" />
            <Skeleton w="80%" h={10} />
          </div>
        </div>
      ))}
    </div>
  )
}

export function SkeletonStats({ count = 4 }) {
  return (
    <div className="grid stats" role="status" aria-label="กำลังโหลด">
      {Array.from({ length: count }).map((_, i) => (
        <div className="statcard" key={i}>
          <Skeleton w="50%" h={22} />
          <Skeleton w="70%" h={10} style={{ marginTop: 8 }} />
        </div>
      ))}
    </div>
  )
}

export function Stat({ label, value, sub }) {
  return (
    <div className="statcard">
      <div className="statval">{value ?? '–'}</div>
      <div className="statlabel">{label}</div>
      {sub != null && <div className="muted sm">{sub}</div>}
    </div>
  )
}
