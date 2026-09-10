import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, Navigate, useLocation } from 'react-router-dom'
import { initAuth, logout } from './lib/auth.js'
import { api } from './lib/api.js'
import { ToastProvider } from './lib/ui.jsx'
import { ProgressProvider, TopLoader } from './lib/progress.jsx'
import Dashboard from './pages/Dashboard.jsx'
import RichMenus from './pages/RichMenus.jsx'
import RichMenuHistory from './pages/RichMenuHistory.jsx'
import Messaging from './pages/Messaging.jsx'
import Inbox from './pages/Inbox.jsx'
import Slips from './pages/Slips.jsx'
import Registrations from './pages/Registrations.jsx'
import Tasks from './pages/Tasks.jsx'
import Classes from './pages/Classes.jsx'
import AutoReply from './pages/AutoReply.jsx'
import Postbacks from './pages/Postbacks.jsx'
import Automations from './pages/Automations.jsx'
import Segments from './pages/Segments.jsx'
import Users from './pages/Users.jsx'
import Stats from './pages/Stats.jsx'
import Events from './pages/Events.jsx'
import Links from './pages/Links.jsx'
import Liff from './pages/Liff.jsx'
import Admins from './pages/Admins.jsx'

const NAV = [
  ['/', 'แดชบอร์ด', '🏠'],
  ['/inbox', 'กล่องข้อความ', '💬'],
  ['/slips', 'สลิปโอนเงิน', '🧾'],
  ['/registrations', 'ผู้ลงทะเบียน', '📝'],
  ['/tasks', 'งาน / ติดตาม', '✅'],
  ['/classes', 'คลาส / รุ่น', '🎓'],
  ['/messaging', 'ส่งข้อความ', '✈️'],
  ['/richmenus', 'Rich Menu', '📱'],
  ['/richmenus/history', 'ประวัติ Rich Menu', '🕓'],
  ['/auto-reply', 'ตอบอัตโนมัติ', '🤖'],
  ['/postbacks', 'Postback', '🔘'],
  ['/automations', 'Automation', '⚡'],
  ['/segments', 'กลุ่มเป้าหมาย', '🎯'],
  ['/users', 'ผู้ใช้', '👥'],
  ['/stats', 'สถิติ', '📊'],
  ['/links', 'ลิงก์', '🔗'],
  ['/events', 'Events', '📋'],
  ['/liff', 'LIFF', '📱'],
  ['/admins', 'ผู้ดูแล & ระบบ', '🔑'],
]

function BootScreen({ children }) {
  return (
    <div className="boot">
      <div className="boot-logo">LINE Console</div>
      {children}
    </div>
  )
}

export default function App() {
  const [state, setState] = useState({ loading: true })
  const [drawer, setDrawer] = useState(false)
  const loc = useLocation()

  useEffect(() => {
    initAuth()
      .then(() => api.me())
      .then((me) => setState({ loading: false, me }))
      .catch((e) => setState({ loading: false, error: e.message }))
  }, [])

  useEffect(() => { setDrawer(false) }, [loc.pathname])

  if (state.loading)
    return <BootScreen><div className="boot-bar"><div /></div><p className="muted sm">กำลังเข้าสู่ระบบด้วย LINE…</p></BootScreen>
  if (state.error)
    return (
      <BootScreen>
        <strong>เข้าใช้งานไม่ได้</strong>
        <p className="muted sm">{state.error}</p>
        <button onClick={logout}>ออกจากระบบ</button>
      </BootScreen>
    )

  const current = NAV.find(([to]) => to === loc.pathname) || NAV[0]

  return (
    <ProgressProvider>
      <ToastProvider>
        <TopLoader />

        {/* mobile topbar */}
        <header className="mtop">
          <button className="mtop-btn" onClick={() => setDrawer(true)} aria-label="เมนู">☰</button>
          <span className="mtop-title">{current[2]} {current[1]}</span>
          {state.me.picture && <img className="mtop-ava" src={state.me.picture} alt="" />}
        </header>

        <div className="layout">
          {/* drawer overlay (mobile) */}
          {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} />}

          <aside className={drawer ? 'open' : ''}>
            <div className="brand">LINE Console</div>
            <nav>
              {NAV.map(([to, label, icon]) => (
                <NavLink key={to} to={to} end={to === '/' || to === '/richmenus'}>
                  <span className="nav-ico">{icon}</span>{label}
                </NavLink>
              ))}
            </nav>
            <div className="me">
              {state.me.picture && <img src={state.me.picture} alt="" />}
              <div className="me-info">
                <div className="sm ellipsis">{state.me.name}</div>
                <div className="muted xs">{state.me.role}</div>
              </div>
              <button className="xs" onClick={logout}>ออก</button>
            </div>
          </aside>

          <main>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/richmenus" element={<RichMenus />} />
              <Route path="/richmenus/history" element={<RichMenuHistory />} />
              <Route path="/messaging" element={<Messaging />} />
              <Route path="/inbox" element={<Inbox />} />
              <Route path="/slips" element={<Slips />} />
              <Route path="/registrations" element={<Registrations />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/classes" element={<Classes />} />
              <Route path="/auto-reply" element={<AutoReply />} />
              <Route path="/postbacks" element={<Postbacks />} />
              <Route path="/automations" element={<Automations />} />
              <Route path="/segments" element={<Segments />} />
              <Route path="/users" element={<Users />} />
              <Route path="/stats" element={<Stats />} />
              <Route path="/events" element={<Events />} />
              <Route path="/links" element={<Links />} />
              <Route path="/liff" element={<Liff />} />
              <Route path="/admins" element={<Admins me={state.me} />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </main>
        </div>

        {/* bottom nav (mobile) */}
        <nav className="bnav">
          {NAV.slice(0, 5).map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === '/' || to === '/richmenus'}>
              <span>{icon}</span><small>{label}</small>
            </NavLink>
          ))}
        </nav>
      </ToastProvider>
    </ProgressProvider>
  )
}
