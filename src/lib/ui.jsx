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

export function Spinner({ label = 'กำลังโหลด…' }) {
  return <div className="center muted">{label}</div>
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
