import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import { initAuth, logout } from './lib/auth.js'
import { api } from './lib/api.js'
import { ToastProvider, Spinner } from './lib/ui.jsx'
import Dashboard from './pages/Dashboard.jsx'
import RichMenus from './pages/RichMenus.jsx'
import Messaging from './pages/Messaging.jsx'
import AutoReply from './pages/AutoReply.jsx'
import Segments from './pages/Segments.jsx'
import Users from './pages/Users.jsx'
import Stats from './pages/Stats.jsx'
import Events from './pages/Events.jsx'
import Admins from './pages/Admins.jsx'

const NAV = [
  ['/', 'แดชบอร์ด'],
  ['/richmenus', 'Rich Menu'],
  ['/messaging', 'ส่งข้อความ'],
  ['/auto-reply', 'ตอบอัตโนมัติ'],
  ['/segments', 'กลุ่มเป้าหมาย'],
  ['/users', 'ผู้ใช้'],
  ['/stats', 'สถิติ'],
  ['/events', 'Events'],
  ['/admins', 'ผู้ดูแล'],
]

export default function App() {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    initAuth()
      .then(() => api.me())
      .then((me) => setState({ loading: false, me }))
      .catch((e) => setState({ loading: false, error: e.message }))
  }, [])

  if (state.loading) return <div className="center">กำลังเข้าสู่ระบบด้วย LINE…</div>
  if (state.error)
    return (
      <div className="center">
        <strong>เข้าใช้งานไม่ได้</strong>
        <p className="muted">{state.error}</p>
        <button onClick={logout}>ออกจากระบบ</button>
      </div>
    )

  return (
    <ToastProvider>
      <div className="layout">
        <aside>
          <div className="brand">LINE Console</div>
          <nav>
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === '/'}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="me">
            {state.me.picture && <img src={state.me.picture} alt="" />}
            <div>
              <div className="sm">{state.me.name}</div>
              <div className="muted xs">{state.me.role}</div>
            </div>
            <button className="xs" onClick={logout}>ออก</button>
          </div>
        </aside>
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/richmenus" element={<RichMenus />} />
            <Route path="/messaging" element={<Messaging />} />
            <Route path="/auto-reply" element={<AutoReply />} />
            <Route path="/segments" element={<Segments />} />
            <Route path="/users" element={<Users />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/events" element={<Events />} />
            <Route path="/admins" element={<Admins me={state.me} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </ToastProvider>
  )
}
