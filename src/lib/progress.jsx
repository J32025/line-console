import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'
import { onNetActivity } from './api.js'

const Ctx = createContext(null)
export const useProgress = () => useContext(Ctx)

export function ProgressProvider({ children }) {
  const [net, setNet] = useState(0)          // จำนวน request ที่กำลังวิ่ง (top bar)
  const [task, setTask] = useState(null)     // { label, done, total, sub }
  const raf = useRef(0)

  // ผูกกับ api.js: ทุก fetch เพิ่ม/ลด counter
  useEffect(() => onNetActivity((delta) => setNet((n) => Math.max(0, n + delta))), [])

  const start = useCallback((label, total = 0) => {
    const state = { label, done: 0, total, sub: '' }
    setTask({ ...state })
    const push = () => {
      cancelAnimationFrame(raf.current)
      raf.current = requestAnimationFrame(() => setTask({ ...state }))
    }
    return {
      advance(n = 1, sub) { state.done += n; if (sub != null) state.sub = sub; push() },
      set(done, sub) { state.done = done; if (sub != null) state.sub = sub; push() },
      setTotal(t) { state.total = t; push() },
      label(l) { state.label = l; push() },
      done() { cancelAnimationFrame(raf.current); setTask(null) },
    }
  }, [])

  // wrap promise ให้ขึ้น top bar เฉย ๆ
  const wrap = useCallback(async (p) => {
    setNet((n) => n + 1)
    try { return await p } finally { setNet((n) => Math.max(0, n - 1)) }
  }, [])

  return (
    <Ctx.Provider value={{ start, wrap, net }}>
      {children}
      <TopLoaderInner active={net > 0} />
      {task && <TaskOverlay task={task} />}
    </Ctx.Provider>
  )
}

// top bar อยู่ใน provider แล้ว — export ตัวเปล่าไว้เผื่อวางเพิ่ม
export function TopLoader() { return null }

function TopLoaderInner({ active }) {
  const [w, setW] = useState(0)
  const [show, setShow] = useState(false)
  useEffect(() => {
    let id
    if (active) {
      setShow(true); setW(8)
      id = setInterval(() => setW((x) => (x < 90 ? x + (90 - x) * 0.15 : x)), 300)
    } else if (show) {
      setW(100)
      const t = setTimeout(() => { setShow(false); setW(0) }, 350)
      return () => clearTimeout(t)
    }
    return () => clearInterval(id)
  }, [active]) // eslint-disable-line
  if (!show) return null
  return <div className="toploader"><div style={{ width: `${w}%` }} /></div>
}

function TaskOverlay({ task }) {
  const pct = task.total ? Math.min(100, Math.round((task.done / task.total) * 100)) : null
  return (
    <div className="task-scrim">
      <div className="task-card">
        <div className="task-spin" />
        <div className="task-label">{task.label}</div>
        {pct != null ? (
          <>
            <div className="task-bar"><div style={{ width: `${pct}%` }} /></div>
            <div className="task-pct">{pct}% <span className="muted">({task.done.toLocaleString()}/{task.total.toLocaleString()})</span></div>
          </>
        ) : (
          <div className="task-bar indeterminate"><div /></div>
        )}
        {task.sub && <div className="muted xs">{task.sub}</div>}
      </div>
    </div>
  )
}

// bar แบบ inline ใช้ในหน้าอื่น
export function ProgressBar({ value, total, label }) {
  const pct = total ? Math.min(100, Math.round((value / total) * 100)) : 0
  return (
    <div className="pbar-wrap">
      {label && <div className="row spread xs"><span>{label}</span><span>{pct}%</span></div>}
      <div className="task-bar"><div style={{ width: `${pct}%` }} /></div>
    </div>
  )
}
