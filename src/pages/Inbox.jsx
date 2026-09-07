import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, InlineSpinner, SkeletonRows } from '../lib/ui.jsx'
import MessagePreview from '../components/MessagePreview.jsx'

const FILTERS = [['all', 'ทั้งหมด'], ['unread', 'ยังไม่อ่าน'], ['mine', 'ของฉัน'], ['paused', 'หยุด AI']]

export default function Inbox() {
  const t = useToast()
  const [convs, setConvs] = useState(null)
  const [filter, setFilter] = useState('all')
  const [totalUnread, setTotalUnread] = useState(0)
  const [sel, setSel] = useState(null)       // uid
  const [thread, setThread] = useState(null) // {user, messages}
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)

  const loadConvs = () => api.inbox({ filter, limit: 60 })
    .then((d) => { setConvs(d.conversations); setTotalUnread(d.total_unread) })
    .catch((e) => t.err(e.message))

  useEffect(() => { loadConvs() }, [filter]) // eslint-disable-line
  useEffect(() => {
    const id = setInterval(loadConvs, 15000) // poll
    return () => clearInterval(id)
  }, [filter]) // eslint-disable-line

  const openThread = async (uid) => {
    setSel(uid); setThread(null)
    try {
      const d = await api.thread(uid, { limit: 60 })
      setThread(d)
      if (d.user.unread) { api.threadRead(uid).then(loadConvs) }
      setTimeout(() => bottomRef.current?.scrollIntoView(), 50)
    } catch (e) { t.err(e.message) }
  }

  // poll เปิดอยู่
  useEffect(() => {
    if (!sel) return
    const id = setInterval(async () => {
      try {
        const d = await api.thread(sel, { limit: 60 })
        setThread((prev) => (prev && d.messages.length !== prev.messages.length
          ? (setTimeout(() => bottomRef.current?.scrollIntoView(), 50), d) : d))
      } catch {}
    }, 8000)
    return () => clearInterval(id)
  }, [sel])

  const send = async () => {
    if (!text.trim()) return
    setBusy(true)
    try {
      await api.threadSend(sel, [text])
      setText('')
      const d = await api.thread(sel, { limit: 60 }); setThread(d)
      setTimeout(() => bottomRef.current?.scrollIntoView(), 50)
      loadConvs()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const togglePause = async () => {
    const next = !thread.user.auto_reply_paused
    try {
      await api.threadPause(sel, next)
      const d = await api.thread(sel, { limit: 60 }); setThread(d); loadConvs()
      t.ok(next ? 'หยุดตอบอัตโนมัติ — คุณคุยเอง' : 'เปิดตอบอัตโนมัติแล้ว')
    } catch (e) { t.err(e.message) }
  }

  return (
    <div>
      <h1>กล่องข้อความ {totalUnread > 0 && <span className="chip failed">{totalUnread} ใหม่</span>}</h1>

      <div className="inbox">
        {/* ---- รายการแชต ---- */}
        <div className="inbox-list card">
          <div className="row wrap" style={{ marginBottom: 8 }}>
            {FILTERS.map(([v, l]) => (
              <button key={v} className={filter === v ? 'xs primary' : 'xs'} onClick={() => setFilter(v)}>{l}</button>
            ))}
          </div>
          {!convs ? <SkeletonRows rows={8} cols={1} /> : convs.length === 0 ? (
            <p className="muted center sm">ยังไม่มีบทสนทนา<br />(รอ user ทักเข้ามา — ต้องตั้ง Webhook)</p>
          ) : convs.map((c) => (
            <div key={c.line_user_id}
                 className={`conv ${sel === c.line_user_id ? 'active' : ''} ${c.unread ? 'unread' : ''}`}
                 onClick={() => openThread(c.line_user_id)}>
              <img src={c.picture_url || FALLBACK} alt="" />
              <div className="conv-body">
                <div className="conv-top">
                  <b className="ellipsis">{c.display_name || c.line_user_id.slice(0, 10)}</b>
                  <span className="muted xs">{fmtShort(c.last_message_at)}</span>
                </div>
                <div className="conv-last ellipsis">
                  {c.auto_reply_paused && <span className="chip" style={{ marginRight: 4 }}>คุยเอง</span>}
                  {c.last_message_text}
                </div>
              </div>
              {c.unread > 0 && <span className="conv-badge">{c.unread}</span>}
            </div>
          ))}
        </div>

        {/* ---- thread ---- */}
        <div className="inbox-thread card">
          {!sel ? (
            <p className="muted center">เลือกบทสนทนาทางซ้าย</p>
          ) : !thread ? (
            <SkeletonRows rows={6} cols={1} />
          ) : (
            <>
              <div className="thread-head">
                <img src={thread.user.picture_url || FALLBACK} alt="" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <b className="ellipsis">{thread.user.display_name || sel.slice(0, 12)}</b>
                  <div className="muted xs ellipsis">{thread.user.status_message || sel}</div>
                </div>
                <button className={thread.user.auto_reply_paused ? 'sm primary' : 'sm'} onClick={togglePause}>
                  {thread.user.auto_reply_paused ? '▶ เปิด AI' : '⏸ หยุด AI คุยเอง'}
                </button>
              </div>

              <div className="thread-body">
                {thread.messages.map((m) => (
                  <div key={m.id} className={`tmsg ${m.direction}`}>
                    {m.by === 'system' ? (
                      <div className="tmsg-sys">{m.text}</div>
                    ) : (
                      <div className="tmsg-wrap">
                        {m.media_url
                          ? <img className="tmsg-img" src={m.media_url} alt="" onClick={() => window.open(m.media_url, '_blank')} />
                          : m.payload && m.msg_type !== 'text'
                            ? <MessagePreview msg={m.payload} />
                            : <div className="tmsg-bubble">{m.text}</div>}
                        <div className="tmsg-meta">
                          {m.direction === 'out' && (m.by === 'auto' ? '🤖 auto' : m.by === 'system' ? 'system' : 'แอดมิน')}
                          {' · '}{fmtShort(m.created_at)}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              <div className="thread-compose">
                <textarea rows={2} placeholder="พิมพ์ข้อความ… (push — กินโควตา)"
                          value={text} onChange={(e) => setText(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send() }} />
                <button className="primary" onClick={send} disabled={busy}>
                  {busy ? <InlineSpinner /> : 'ส่ง'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

const FALLBACK = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2280%22%3E%3Crect width=%2280%22 height=%2280%22 fill=%22%23dfe3e8%22/%3E%3C/svg%3E'
function fmtShort(s) {
  if (!s) return ''
  const d = new Date(s), now = new Date()
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })
}
