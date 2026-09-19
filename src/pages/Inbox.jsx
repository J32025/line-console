import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, InlineSpinner, SkeletonRows } from '../lib/ui.jsx'
import MessagePreview from '../components/MessagePreview.jsx'

const PRESETS = [
  ['slips', '🧾 ส่งสลิป'],
  ['all', 'ทั้งหมด'],
  ['unread', 'ยังไม่อ่าน'],
  ['mine', 'ของฉัน'],
  ['paused', 'หยุด AI'],
  ['unfollowed', 'เลิกติดตาม'],
]
const SORTS = [['recent', 'ล่าสุดก่อน'], ['unread_first', 'ยังไม่อ่านก่อน'], ['oldest', 'เก่าสุดก่อน']]
const STAGES = [['', 'ทุกสถานะ'], ['none', '(ไม่มี)'], ['lead', 'Lead'], ['interested', 'สนใจ'],
  ['registered', 'ลงทะเบียน'], ['paid', 'จ่ายแล้ว'], ['enrolled', 'เข้าเรียน'],
  ['completed', 'เรียนจบ'], ['alumni', 'ศิษย์เก่า'], ['lost', 'หลุด']]
const STAGE_LABEL = Object.fromEntries(STAGES)
// ตัวเลือกสำหรับ "ตั้งสถานะ" ของคนคนเดียว (ไม่มี "ทุกสถานะ" เพราะไม่เกี่ยวกับ filter)
const STAGE_SET_OPTS = [['', '(ไม่มีสถานะ)'], ...STAGES.slice(2)]
const FOLLOWING = [['', 'ทั้งหมด'], ['true', 'ติดตามอยู่'], ['false', 'เลิกติดตามแล้ว']]
const CONSENT = [['', 'ทั้งหมด'], ['true', 'ยินยอมรับข่าว'], ['false', 'ปฏิเสธ/ยกเลิก'], ['unknown', 'ไม่ทราบ']]
const EMPTY_ADV = { q: '', tag: '', stage: '', menu: '', assigned: '', following: '', consent: '', sort: 'recent' }
const LS_KEY = 'lc_inbox_filters'

export default function Inbox() {
  const t = useToast()
  const [convs, setConvs] = useState(null)
  const [counts, setCounts] = useState({})
  const [filter, setFilter] = useState('all')
  const [adv, setAdv] = useState(() => {
    try { return { ...EMPTY_ADV, ...JSON.parse(localStorage.getItem(LS_KEY) || '{}') } } catch { return EMPTY_ADV }
  })
  const [qInput, setQInput] = useState(adv.q)
  const [showAdv, setShowAdv] = useState(false)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [totalUnread, setTotalUnread] = useState(0)
  const [admins, setAdmins] = useState([])
  const [menus, setMenus] = useState([])
  const [tagOptions, setTagOptions] = useState([])
  const [sel, setSel] = useState(null)       // uid
  const [thread, setThread] = useState(null) // {user, messages}
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)
  const limit = 60

  const activeAdvCount = useMemo(() => Object.entries(adv).filter(([k, v]) => k !== 'sort' && v).length, [adv])

  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(adv)) } catch {}
  }, [adv])

  useEffect(() => {
    api.admins().then((d) => setAdmins(d.admins)).catch(() => {})
    api.richmenuUsage().then((d) => setMenus(d.items || [])).catch(() => {})
    api.inboxTags().then((d) => setTagOptions(d.tags || [])).catch(() => {})
  }, [])

  const loadConvs = (nextOffset = 0, append = false) => {
    const qs = { filter, limit, offset: nextOffset, ...adv }
    Object.keys(qs).forEach((k) => qs[k] === '' && delete qs[k])
    if (append) setLoadingMore(true)
    return api.inbox(qs)
      .then((d) => {
        setConvs((prev) => append ? [...(prev || []), ...d.conversations] : d.conversations)
        setTotalUnread(d.total_unread); setCounts(d.counts || {})
        setHasMore(d.conversations.length === limit)
        setOffset(nextOffset)
      })
      .catch((e) => t.err(e.message))
      .finally(() => { if (append) setLoadingMore(false) })
  }

  useEffect(() => { setConvs(null); loadConvs(0, false) }, [filter, adv]) // eslint-disable-line
  useEffect(() => {
    // poll — ข้ามตอนซ่อนแท็บ (ทุกรอบ = 1 invocation ของ Vercel + หลาย query)
    const id = setInterval(() => { if (!document.hidden) loadConvs(0, false) }, 30000)
    return () => clearInterval(id)
  }, [filter, adv]) // eslint-disable-line

  const runSearch = () => setAdv((a) => ({ ...a, q: qInput.trim() }))
  const resetAdv = () => { setAdv(EMPTY_ADV); setQInput('') }

  const openThread = async (uid) => {
    setSel(uid); setThread(null)
    try {
      const d = await api.thread(uid, { limit: 60 })
      setThread(d)
      if (d.user.unread) { api.threadRead(uid).then(() => loadConvs(0, false)) }
      setTimeout(() => bottomRef.current?.scrollIntoView(), 50)
    } catch (e) { t.err(e.message) }
  }

  // poll เปิดอยู่
  useEffect(() => {
    if (!sel) return
    const id = setInterval(async () => {
      if (document.hidden) return
      try {
        const d = await api.thread(sel, { limit: 60 })
        setThread((prev) => (prev && d.messages.length !== prev.messages.length
          ? (setTimeout(() => bottomRef.current?.scrollIntoView(), 50), d) : d))
      } catch {}
    }, 12000)
    return () => clearInterval(id)
  }, [sel])

  const send = async () => {
    if (!text.trim()) return
    setBusy(true)
    try {
      const r = await api.threadSend(sel, [text])
      setText('')
      const d = await api.thread(sel, { limit: 60 }); setThread(d)
      setTimeout(() => bottomRef.current?.scrollIntoView(), 50)
      loadConvs(0, false)
      if (r?.kb_draft_hint) t.info(`🧠 ${r.kb_draft_hint}`, 'ok')
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const togglePause = async () => {
    const next = !thread.user.auto_reply_paused
    try {
      await api.threadPause(sel, next)
      const d = await api.thread(sel, { limit: 60 }); setThread(d); loadConvs(0, false)
      t.ok(next ? 'หยุดตอบอัตโนมัติ — คุณคุยเอง' : 'เปิดตอบอัตโนมัติแล้ว')
    } catch (e) { t.err(e.message) }
  }

  const assignTo = async (to) => {
    try {
      await api.threadAssign(sel, to || null)
      const d = await api.thread(sel, { limit: 60 }); setThread(d); loadConvs(0, false)
      t.ok(to ? 'มอบหมายแล้ว' : 'เอาผู้รับผิดชอบออกแล้ว')
    } catch (e) { t.err(e.message) }
  }

  const setStage = async (stage) => {
    try {
      await api.updateUser(sel, { stage: stage || null })
      const d = await api.thread(sel, { limit: 60 }); setThread(d)
      t.ok('อัปเดตสถานะแล้ว')
    } catch (e) { t.err(e.message) }
  }

  return (
    <div>
      <h1>กล่องข้อความ {totalUnread > 0 && <span className="chip failed">{totalUnread} ใหม่</span>}</h1>

      <div className="inbox">
        {/* ---- รายการแชต ---- */}
        <div className="inbox-list card">
          <div className="row wrap" style={{ marginBottom: 6 }}>
            {PRESETS.map(([v, l]) => (
              <button key={v} className={filter === v ? 'xs primary' : 'xs'} onClick={() => setFilter(v)}>
                {l}{counts[v] > 0 && <span className="muted"> {counts[v]}</span>}
              </button>
            ))}
          </div>
          <div className="row wrap" style={{ marginBottom: 8, alignItems: 'center' }}>
            <button className={`xs ${showAdv ? 'primary' : ''}`} onClick={() => setShowAdv((v) => !v)}>
              🔍 ตัวกรอง{activeAdvCount > 0 && ` (${activeAdvCount})`}
            </button>
            <select className="xs" value={adv.sort} onChange={(e) => setAdv((a) => ({ ...a, sort: e.target.value }))}>
              {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            {activeAdvCount > 0 && <button className="xs" onClick={resetAdv}>ล้างตัวกรอง</button>}
          </div>

          {showAdv && (
            <div className="inbox-filters">
              <div className="row" style={{ gap: 4 }}>
                <input placeholder="ค้นหาชื่อ / userId / note" value={qInput}
                       onChange={(e) => setQInput(e.target.value)}
                       onKeyDown={(e) => e.key === 'Enter' && runSearch()} style={{ flex: 1 }} />
                <button className="xs" onClick={runSearch}>ค้นหา</button>
              </div>
              <input list="inbox-tag-opts" placeholder="แท็ก" value={adv.tag}
                     onChange={(e) => setAdv((a) => ({ ...a, tag: e.target.value }))} />
              <datalist id="inbox-tag-opts">
                {tagOptions.map((tg) => <option key={tg} value={tg} />)}
              </datalist>
              <select value={adv.stage} onChange={(e) => setAdv((a) => ({ ...a, stage: e.target.value }))}>
                {STAGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <select value={adv.menu} onChange={(e) => setAdv((a) => ({ ...a, menu: e.target.value }))}>
                <option value="">ทุกเมนู</option>
                <option value="none">(ไม่มีเมนู)</option>
                {menus.filter((m) => m.richMenuId).map((m) => <option key={m.richMenuId} value={m.richMenuId}>{m.name} ({m.count})</option>)}
              </select>
              <select value={adv.assigned} onChange={(e) => setAdv((a) => ({ ...a, assigned: e.target.value }))}>
                <option value="">ทุกคนที่รับผิดชอบ</option>
                <option value="none">(ยังไม่มอบหมาย)</option>
                {admins.map((a) => <option key={a.line_user_id} value={a.line_user_id}>{a.name || a.line_user_id.slice(0, 10)}</option>)}
              </select>
              <select value={adv.following} onChange={(e) => setAdv((a) => ({ ...a, following: e.target.value }))}>
                {FOLLOWING.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <select value={adv.consent} onChange={(e) => setAdv((a) => ({ ...a, consent: e.target.value }))}>
                {CONSENT.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          )}

          {!convs ? <SkeletonRows rows={8} cols={1} /> : convs.length === 0 ? (
            <p className="muted center sm">ไม่พบบทสนทนาตามตัวกรองนี้</p>
          ) : (
            <>
              {convs.map((c) => (
                <div key={c.line_user_id}
                     className={`conv ${sel === c.line_user_id ? 'active' : ''} ${c.unread ? 'unread' : ''} ${!c.is_following ? 'conv-unfollowed' : ''}`}
                     onClick={() => openThread(c.line_user_id)}>
                  <img src={c.picture_url || FALLBACK} alt="" />
                  <div className="conv-body">
                    <div className="conv-top">
                      <b className="ellipsis">{c.display_name || c.line_user_id.slice(0, 10)}</b>
                      <span className="muted xs">{fmtShort(c.last_message_at)}</span>
                    </div>
                    <div className="conv-last ellipsis">
                      {c.slip_pending > 0 && <span className="chip partial" style={{ marginRight: 4 }} title="มีสลิปรอตรวจ">🧾 รอตรวจ{c.slip_pending > 1 ? ` x${c.slip_pending}` : ''}</span>}
                      {c.auto_reply_paused && <span className="chip" style={{ marginRight: 4 }}>คุยเอง</span>}
                      {!c.is_following && <span className="chip failed" style={{ marginRight: 4 }}>เลิกติดตาม</span>}
                      {c.last_message_text}
                    </div>
                    {(c.stage || (c.tags && c.tags.length > 0)) && (
                      <div className="row wrap" style={{ gap: 3, marginTop: 2 }}>
                        {c.stage && <span className="chip xs">{STAGE_LABEL[c.stage] || c.stage}</span>}
                        {(c.tags || []).slice(0, 3).map((tg) => <span key={tg} className="chip xs muted">{tg}</span>)}
                        {(c.tags || []).length > 3 && <span className="muted xs">+{c.tags.length - 3}</span>}
                      </div>
                    )}
                  </div>
                  {c.unread > 0 && <span className="conv-badge">{c.unread}</span>}
                </div>
              ))}
              {hasMore && (
                <button className="xs" style={{ width: '100%', marginTop: 6 }}
                        disabled={loadingMore} onClick={() => loadConvs(offset + limit, true)}>
                  {loadingMore ? <InlineSpinner /> : 'โหลดเพิ่ม'}
                </button>
              )}
            </>
          )}
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
                  <div className="muted xs ellipsis">
                    {thread.user.status_message || sel}
                    {!thread.user.is_following && <span className="chip failed xs" style={{ marginLeft: 6 }}>เลิกติดตาม</span>}
                  </div>
                </div>
                <select className="xs" value={thread.user.stage || ''} onChange={(e) => setStage(e.target.value)} title="สถานะ pipeline">
                  {STAGE_SET_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <select className="xs" value={thread.user.assigned_to || ''} onChange={(e) => assignTo(e.target.value)} title="มอบหมายให้">
                  <option value="">(ยังไม่มอบหมาย)</option>
                  {admins.map((a) => <option key={a.line_user_id} value={a.line_user_id}>{a.name || a.line_user_id.slice(0, 10)}</option>)}
                </select>
                <button className={thread.user.auto_reply_paused ? 'sm primary' : 'sm'} onClick={togglePause}>
                  {thread.user.auto_reply_paused ? '▶ เปิด AI' : '⏸ หยุด AI คุยเอง'}
                </button>
              </div>

              {thread.user.tags?.length > 0 && (
                <div className="row wrap" style={{ gap: 4, padding: '6px 10px', borderBottom: '1px solid var(--border)' }}>
                  {thread.user.tags.map((tg) => <span key={tg} className="chip xs muted">{tg}</span>)}
                </div>
              )}

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
                          {m.direction === 'out' && ({ auto: '🤖 auto', gemini: '🤖 AI', automation: '⚡ automation',
                            postback: '🔘 ปุ่ม', broadcast: '✈️ broadcast', system: 'system' }[m.by] || 'แอดมิน')}
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
