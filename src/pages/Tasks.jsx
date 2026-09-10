import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, Stat, useToast } from '../lib/ui.jsx'

const nf = (n) => (n == null ? '–' : Number(n).toLocaleString('th-TH'))
const TABS = [['me', 'ของฉัน'], ['open', 'ทั้งหมด (ค้าง)'], ['overdue', 'เกินกำหนด'], ['done', 'เสร็จแล้ว']]
const TAGS = ['ติดตาม', 'จ่ายเงิน', 'โทร', 'เอกสาร', 'อื่น ๆ']
const dueClass = (t) => {
  if (t.status !== 'open' || !t.due_at) return ''
  return new Date(t.due_at) < new Date() ? 'chip failed' : 'chip'
}
const fmtDue = (s) => s ? new Date(s).toLocaleString('th-TH', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '–'

export default function Tasks() {
  const t = useToast()
  const nav = useNavigate()
  const [tab, setTab] = useState('me')
  const [list, setList] = useState(null)
  const [sum, setSum] = useState(null)
  const [add, setAdd] = useState(null)
  const [busy, setBusy] = useState(false)
  const [hint, setHint] = useState('')

  const loadSum = () => api.tasksSummary().then(setSum).catch(() => {})
  const load = () => {
    setList(null); setHint('')
    const qs = tab === 'me' ? { status: 'open', assignee: 'me' }
      : tab === 'overdue' ? { overdue: 1 }
        : tab === 'done' ? { status: 'done' } : { status: 'open' }
    api.tasks(qs).then((d) => { setList(d.tasks); if (d.schema_missing) setHint(d.hint) }).catch((e) => t.err(e.message))
  }
  useEffect(() => { loadSum() }, [])
  useEffect(() => { load() }, [tab]) // eslint-disable-line

  const patch = async (id, p) => {
    try { await api.updateTask(id, p); load(); loadSum() } catch (e) { t.err(e.message) }
  }
  const create = async () => {
    if (!add.title.trim()) return t.err('ใส่ชื่องาน')
    setBusy(true)
    try {
      await api.createTask({ ...add, dueAt: add.dueAt || null })
      t.ok('สร้างงานแล้ว'); setAdd(null); load(); loadSum()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="row spread wrap" style={{ alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>งาน / ติดตาม</h1>
        <button className="sm primary" onClick={() => setAdd({ title: '', detail: '', dueAt: '', priority: 'normal', tag: 'ติดตาม', lineUserId: '' })}>+ งานใหม่</button>
      </div>

      {sum && (
        <div className="grid stats">
          <Stat label="ค้างทั้งหมด" value={nf(sum.open)} />
          <Stat label="เกินกำหนด" value={nf(sum.overdue)} sub={sum.overdue ? '⚠ ต้องรีบ' : 'ไม่มี'} />
          <Stat label="ของฉัน (ค้าง)" value={nf(sum.mine)} />
          <Stat label="เสร็จวันนี้" value={nf(sum.done_today)} />
        </div>
      )}

      <div className="dash-nav" style={{ position: 'static', border: 0 }}>
        {TABS.map(([k, l]) => <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {hint && <p className="err">{hint}</p>}

      <section className="card">
        {!list ? <Spinner /> : list.length === 0 ? <p className="muted center">{hint ? 'รัน migration ก่อน' : 'ไม่มีงาน'}</p> : (
          <ul className="loglist">
            {list.map((k) => (
              <li key={k.id} style={{ opacity: k.status === 'done' ? 0.5 : 1, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <input type="checkbox" checked={k.status === 'done'}
                       onChange={(e) => patch(k.id, { status: e.target.checked ? 'done' : 'open' })}
                       style={{ marginTop: 3 }} />
                <div style={{ flex: 1, minWidth: 180 }}>
                  <div style={{ textDecoration: k.status === 'done' ? 'line-through' : 'none' }}>
                    {k.priority === 'high' && '🔴 '}{k.title}
                  </div>
                  <div className="muted xs row wrap" style={{ gap: 6 }}>
                    {k.tag && <span className="chip xs">{k.tag}</span>}
                    {k.due_at && <span className={dueClass(k) + ' xs'}>⏰ {fmtDue(k.due_at)}</span>}
                    {k.user
                      ? <a onClick={() => nav('/users?q=' + k.line_user_id)}>{k.user.display_name || k.line_user_id.slice(0, 10)}</a>
                      : k.line_user_id && <span className="mono">{k.line_user_id.slice(0, 10)}</span>}
                    {k.detail && <span>· {k.detail}</span>}
                  </div>
                </div>
                <div className="row" style={{ gap: 4 }}>
                  {k.status === 'open' && k.line_user_id && (
                    <button className="xs" onClick={() => nav('/inbox')}>แชต</button>
                  )}
                  <button className="xs danger" onClick={async () => {
                    if (!confirm('ลบงานนี้?')) return
                    try { await api.delTask(k.id); load(); loadSum() } catch (e) { t.err(e.message) }
                  }}>ลบ</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {add && (
        <div className="modal-bg" onClick={() => setAdd(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>งานใหม่</h3><button className="xs" onClick={() => setAdd(null)}>✕</button></div>
            <label className="sm">ชื่องาน *</label>
            <input value={add.title} onChange={(e) => setAdd({ ...add, title: e.target.value })} placeholder="เช่น โทรตามคุณสมชาย เรื่องสลิป" />
            <label className="sm">รายละเอียด</label>
            <input value={add.detail} onChange={(e) => setAdd({ ...add, detail: e.target.value })} />
            <div className="row wrap">
              <label>กำหนดเสร็จ&nbsp;<input type="datetime-local" value={add.dueAt} onChange={(e) => setAdd({ ...add, dueAt: e.target.value })} /></label>
              <label>ความสำคัญ&nbsp;
                <select value={add.priority} onChange={(e) => setAdd({ ...add, priority: e.target.value })}>
                  <option value="low">ต่ำ</option><option value="normal">ปกติ</option><option value="high">สูง</option>
                </select>
              </label>
              <label>หมวด&nbsp;
                <select value={add.tag} onChange={(e) => setAdd({ ...add, tag: e.target.value })}>
                  {TAGS.map((x) => <option key={x}>{x}</option>)}
                </select>
              </label>
            </div>
            <label className="sm">LINE userId ที่เกี่ยวข้อง (ถ้ามี)</label>
            <input className="mono" value={add.lineUserId} onChange={(e) => setAdd({ ...add, lineUserId: e.target.value.trim() })} placeholder="U..." />
            <button className="primary" disabled={busy} onClick={create}>{busy && <InlineSpinner />}สร้างงาน</button>
          </div>
        </div>
      )}
    </div>
  )
}
