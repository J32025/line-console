import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, InlineSpinner } from '../lib/ui.jsx'
import { blank } from '../lib/messageTypes.js'
import { useProgress } from '../lib/progress.jsx'
import MessageEditor from '../components/MessageEditor.jsx'
import MessagePreview from '../components/MessagePreview.jsx'
import TemplateGallery from '../components/TemplateGallery.jsx'

const DRAFT_KEY = 'lc_msg_draft'

export default function Messaging() {
  const t = useToast()
  const prog = useProgress()
  const [messages, setMessages] = useState(() => {
    try { const d = JSON.parse(localStorage.getItem(DRAFT_KEY)); if (d?.length) return d } catch {}
    return [blank('text')]
  })
  const [mode, setMode] = useState('broadcast') // broadcast | push | db | segment | narrowcast
  const [to, setTo] = useState('')
  const [tag, setTag] = useState('')
  const [menu, setMenu] = useState('')
  const [segId, setSegId] = useState('')
  const [nc, setNc] = useState({ gender: [], ageGte: '', ageLt: '', areas: [] })
  const [notiOff, setNotiOff] = useState(false)
  const [bulkResult, setBulkResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState([])
  const [usage, setUsage] = useState([])
  const [segments, setSegments] = useState([])
  const [templates, setTemplates] = useState([])
  const [schedAt, setSchedAt] = useState('')
  const [scheduled, setScheduled] = useState([])
  const [preview, setPreview] = useState(null) // {count, sample}
  const [ncProgress, setNcProgress] = useState(null)
  const [gallery, setGallery] = useState(false)

  const loadHistory = () => api.broadcastHistory().then((d) => setHistory(d.broadcasts)).catch(() => {})
  const loadScheduled = () => api.scheduled().then((d) => setScheduled(d.jobs)).catch(() => {})
  const loadTemplates = () => api.get('/message-templates').then((d) => setTemplates(d.templates)).catch(() => {})
  useEffect(() => {
    loadHistory(); loadScheduled(); loadTemplates()
    api.richmenuUsage().then((d) => setUsage(d.items)).catch(() => {})
    api.segments().then((d) => setSegments(d.segments)).catch(() => {})
  }, [])

  // autosave draft
  useEffect(() => {
    const id = setTimeout(() => {
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify(messages)) } catch {}
    }, 800)
    return () => clearTimeout(id)
  }, [messages])

  const targetPayload = () => {
    if (mode === 'segment') return { mode, segmentId: segId }
    if (mode === 'push') return { mode, to }
    if (mode === 'db') return { mode, tag, menu }
    return { mode }
  }
  const doPreview = async () => {
    try { setPreview(await api.post('/message/recipients-preview', targetPayload())) }
    catch (e) { t.err(e.message) }
  }

  const saveTemplate = async () => {
    const name = prompt('ชื่อเทมเพลต:')
    if (!name) return
    try { await api.post('/message-templates', { name, messages }); t.ok('บันทึกเทมเพลตแล้ว'); loadTemplates() }
    catch (e) { t.err(e.message) }
  }
  const loadTemplate = (id) => {
    const tpl = templates.find((x) => String(x.id) === id)
    if (tpl) setMessages(tpl.messages)
  }
  const resend = (b) => { setMessages(b.messages); t.info('โหลดข้อความจากประวัติแล้ว', 'ok'); window.scrollTo(0, 0) }

  const doSchedule = async () => {
    if (!schedAt) return t.err('เลือกเวลาก่อน')
    setBusy(true)
    try {
      await api.schedule({ kind: 'broadcast', runAt: new Date(schedAt).toISOString(), messages })
      t.ok('ตั้งเวลาส่ง broadcast แล้ว'); setSchedAt(''); loadScheduled()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const menus = usage.filter((u) => u.richMenuId)
  const selectedCount = menu
    ? usage.find((u) => u.richMenuId === menu)?.count ?? 0
    : usage.reduce((s, u) => s + (u.richMenuId ? u.count : 0), 0)

  const setMsg = (i, m) => setMessages((arr) => arr.map((x, j) => (j === i ? m : x)))
  const addMsg = () => messages.length < 5 && setMessages((a) => [...a, blank('text')])
  const rmMsg = (i) => setMessages((a) => a.filter((_, j) => j !== i))

  const toIds = to.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)
  const validIds = [...new Set(toIds.filter((u) => /^U[0-9a-f]{32}$/.test(u)))]
  const seg = segments.find((s) => String(s.id) === String(segId))
  const targetLabel = {
    broadcast: 'ทุกคนที่ติดตาม',
    push: `${validIds.length.toLocaleString()} userId${toIds.length !== validIds.length ? ` (${toIds.length - validIds.length} ผิดรูปแบบ)` : ''}`,
    db: `${menu ? menus.find((m) => m.richMenuId === menu)?.name : 'ทุกเมนู'}${tag ? ` +tag:${tag}` : ''} · ~${selectedCount.toLocaleString()} คน`,
    segment: seg ? `${seg.name} · ~${(seg.last_count ?? 0).toLocaleString()} คน` : 'เลือกกลุ่ม',
    narrowcast: `demographic (${nc.gender.join('/') || 'ทุกเพศ'}${nc.ageGte ? ` ${nc.ageGte}+` : ''})`,
  }[mode]

  const buildDemographic = () => {
    const parts = []
    if (nc.gender.length) parts.push({ type: 'gender', oneOf: nc.gender })
    if (nc.ageGte || nc.ageLt) {
      const a = { type: 'age' }
      if (nc.ageGte) a.gte = `age_${nc.ageGte}`
      if (nc.ageLt) a.lt = `age_${nc.ageLt}`
      parts.push(a)
    }
    if (nc.areas.length) parts.push({ type: 'area', oneOf: nc.areas })
    if (!parts.length) return null
    return parts.length === 1 ? parts[0] : { type: 'operator', and: parts }
  }

  const doValidate = async () => {
    try { await api.validateMsg(messages); t.ok('รูปแบบข้อความถูกต้อง ✓') }
    catch (e) { t.err(e.message) }
  }

  const sendTest = async () => {
    setBusy(true)
    try { await api.post('/message/test', { messages }); t.ok('ส่งเข้า LINE ตัวเองแล้ว — เช็คในแอป LINE') }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  // resolve target -> chunk -> bulk send พร้อม % จริง
  const sendToUids = async (kind) => {
    const payload = kind === 'segment' ? { target: 'segment', segmentId: segId } : { target: 'db', tag, menu }
    const { userIds, count } = await api.resolveTarget(payload)
    if (!count) throw new Error('ไม่มีปลายทาง')
    const CHUNK = 2500
    let sent = 0, failed = 0
    const task = prog.start('กำลังส่งข้อความ', count)
    try {
      for (let i = 0; i < userIds.length; i += CHUNK) {
        const pr = await api.bulkSend({ userIds: userIds.slice(i, i + CHUNK), messages })
        sent += pr.sent; failed += pr.failed
        task.set(Math.min(i + CHUNK, count), `ส่งสำเร็จ ${sent.toLocaleString()}`)
      }
    } finally { task.done() }
    return { sent, failed, target: count }
  }

  const send = async () => {
    if (!confirm(`ส่ง ${messages.length} ข้อความ หา ${targetLabel}?`)) return
    setBusy(true)
    try {
      let r
      setBulkResult(null)
      if (mode === 'broadcast') r = await api.broadcast({ messages })
      else if (mode === 'push') {
        // แบ่ง 2500/รอบ (5 batch) แสดง % จริง
        const CHUNK = 2500
        const agg = { total: validIds.length, sent: 0, failed: 0, batches: 0, ok_batches: 0, errors: [], duplicate: toIds.filter((u) => /^U[0-9a-f]{32}$/.test(u)).length - validIds.length, invalid: [], invalid_count: toIds.filter((u) => !/^U[0-9a-f]{32}$/.test(u)).length }
        const task = prog.start('กำลังส่งข้อความ', validIds.length)
        try {
          for (let i = 0; i < validIds.length; i += CHUNK) {
            const part = validIds.slice(i, i + CHUNK)
            const pr = await api.bulkSend({ userIds: part, messages, notificationDisabled: notiOff })
            agg.sent += pr.sent; agg.failed += pr.failed
            agg.batches += pr.batches; agg.ok_batches += pr.ok_batches
            agg.errors.push(...(pr.errors || []))
            task.set(Math.min(i + CHUNK, validIds.length), `ส่งสำเร็จ ${agg.sent.toLocaleString()}`)
          }
        } finally { task.done() }
        r = agg; setBulkResult(agg)
      }
      else if (mode === 'segment') r = await sendToUids('segment')
      else if (mode === 'narrowcast') r = await api.narrowcast({ demographic: buildDemographic(), messages })
      else r = await sendToUids('db')
      t.ok('ส่งแล้ว ' + (r.sent != null ? `(${r.sent.toLocaleString()} คน)` : r.requestId ? `req ${r.requestId.slice(0, 8)}` : ''))
      if (mode === 'narrowcast' && r.requestId) {
        setNcProgress({ requestId: r.requestId, phase: 'waiting' })
        setTimeout(async () => {
          try { setNcProgress({ ...await api.get(`/message/narrowcast/progress?requestId=${r.requestId}`), requestId: r.requestId }) } catch {}
        }, 5000)
      }
      loadHistory()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <h1>ส่งข้อความ</h1>

      <div className="msg-layout">
        {/* ---------- ซ้าย: ตัวแก้ไข ---------- */}
        <div>
          <section className="card">
            <h3>ปลายทาง</h3>
            <div className="row wrap">
              {['broadcast', 'push', 'db', 'segment', 'narrowcast'].map((m) => (
                <label key={m}>
                  <input type="radio" checked={mode === m} onChange={() => setMode(m)} />{' '}
                  {{ broadcast: 'Broadcast', push: 'Push (userId)', db: 'filter DB', segment: 'กลุ่ม', narrowcast: 'Narrowcast (เพศ/อายุ/พื้นที่)' }[m]}
                </label>
              ))}
            </div>
            {mode === 'segment' && (
              <select value={segId} onChange={(e) => setSegId(e.target.value)}>
                <option value="">— เลือกกลุ่ม —</option>
                {segments.map((s) => <option key={s.id} value={s.id}>{s.name} ({(s.last_count ?? 0).toLocaleString()})</option>)}
              </select>
            )}
            {mode === 'narrowcast' && (
              <div className="nc-form">
                <div className="row wrap">
                  <span className="sm muted">เพศ:</span>
                  {['male', 'female'].map((g) => (
                    <label key={g}>
                      <input type="checkbox" checked={nc.gender.includes(g)}
                             onChange={(e) => setNc((s) => ({ ...s, gender: e.target.checked ? [...s.gender, g] : s.gender.filter((x) => x !== g) }))} />
                      {g === 'male' ? ' ชาย' : ' หญิง'}
                    </label>
                  ))}
                </div>
                <div className="row wrap">
                  <span className="sm muted">อายุ:</span>
                  <select value={nc.ageGte} onChange={(e) => setNc((s) => ({ ...s, ageGte: e.target.value }))}>
                    <option value="">ตั้งแต่</option>
                    {['15', '20', '25', '30', '35', '40', '45', '50'].map((a) => <option key={a}>{a}</option>)}
                  </select>
                  <select value={nc.ageLt} onChange={(e) => setNc((s) => ({ ...s, ageLt: e.target.value }))}>
                    <option value="">ถึง (ไม่รวม)</option>
                    {['20', '25', '30', '35', '40', '45', '50'].map((a) => <option key={a}>{a}</option>)}
                  </select>
                </div>
                <p className="muted xs">narrowcast ต้องมีปลายทาง ≥ 100 คน และเป็นแบบ async — เช็คผลใน "ประวัติการส่ง"</p>
              </div>
            )}
            {mode === 'push' && (
              <>
                <textarea rows={5} placeholder="วาง userId เยอะแค่ไหนก็ได้ (คั่นด้วยขึ้นบรรทัด/comma) — ระบบแบ่งส่งทีละ 500 อัตโนมัติ"
                          value={to} onChange={(e) => setTo(e.target.value)} />
                <div className="row wrap">
                  <label className="sm">
                    อัปโหลดไฟล์ .txt/.csv:{' '}
                    <input type="file" accept=".txt,.csv" onChange={(e) => {
                      const f = e.target.files?.[0]; if (!f) return
                      const rd = new FileReader()
                      rd.onload = () => setTo((prev) => (prev ? prev + '\n' : '') + rd.result)
                      rd.readAsText(f)
                    }} />
                  </label>
                  <span className="sm muted">
                    {validIds.length.toLocaleString()} ถูกต้อง
                    {toIds.length !== validIds.length && ` · ${(toIds.length - validIds.length).toLocaleString()} ผิดรูปแบบ`}
                    {validIds.length > 500 && ` · ${Math.ceil(validIds.length / 500)} batch`}
                  </span>
                </div>
              </>
            )}
            {mode === 'db' && (
              <>
                <div className="row wrap">
                  <input placeholder="tag" value={tag} onChange={(e) => setTag(e.target.value)} />
                  <select value={menu} onChange={(e) => setMenu(e.target.value)}>
                    <option value="">— ทุก rich menu ({menus.reduce((s, m) => s + m.count, 0).toLocaleString()} คน) —</option>
                    {menus.map((m) => (
                      <option key={m.richMenuId} value={m.richMenuId}>
                        {m.name} — {m.count.toLocaleString()} คน{m.isDefault ? ' (default)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="usage-bars">
                  {usage.map((u) => {
                    const max = usage[0]?.count || 1
                    return (
                      <div key={u.richMenuId || 'none'} className="usage-row"
                           onClick={() => u.richMenuId && setMenu(u.richMenuId === menu ? '' : u.richMenuId)}
                           style={{ cursor: u.richMenuId ? 'pointer' : 'default' }}>
                        <span className="usage-name">{u.name}</span>
                        <span className="usage-track"><span className="usage-fill" style={{ width: `${(u.count / max) * 100}%` }} /></span>
                        <span className="usage-count">{u.count.toLocaleString()}</span>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </section>

          <section className="card">
            <div className="row spread wrap">
              <h3>ข้อความ ({messages.length}/5)</h3>
              <div className="row wrap">
                <button className="sm primary" onClick={() => setGallery(true)}>📚 คลังเทมเพลต</button>
                <select defaultValue="" onChange={(e) => { loadTemplate(e.target.value); e.target.value = '' }}>
                  <option value="">เทมเพลตของฉัน…</option>
                  {templates.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                </select>
                <button className="xs" onClick={saveTemplate}>บันทึก</button>
                <button className="sm" onClick={addMsg} disabled={messages.length >= 5}>+ ข้อความ</button>
              </div>
            </div>
            {messages.map((m, i) => (
              <MessageEditor key={i} index={i} msg={m}
                             onChange={(nm) => setMsg(i, nm)}
                             onRemove={() => rmMsg(i)} />
            ))}
            <button className="xs" onClick={() => { setMessages([blank('text')]); localStorage.removeItem(DRAFT_KEY) }}>ล้างทั้งหมด</button>
          </section>

          {mode === 'push' && (
            <label className="row"><input type="checkbox" checked={notiOff} onChange={(e) => setNotiOff(e.target.checked)} /> ส่งเงียบ (ไม่เด้งแจ้งเตือน)</label>
          )}

          {bulkResult && (
            <section className="card">
              <h3>ผลการส่งแบบชุด</h3>
              <div className="grid stats" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
                <div className="statcard"><div className="statval">{bulkResult.sent.toLocaleString()}</div><div className="statlabel">ส่งสำเร็จ</div></div>
                <div className="statcard"><div className="statval">{bulkResult.failed.toLocaleString()}</div><div className="statlabel">ล้มเหลว</div></div>
                <div className="statcard"><div className="statval">{bulkResult.ok_batches}/{bulkResult.batches}</div><div className="statlabel">batch สำเร็จ</div></div>
                <div className="statcard"><div className="statval">{(bulkResult.duplicate + bulkResult.invalid_count).toLocaleString()}</div><div className="statlabel">ซ้ำ+ผิดรูปแบบ</div></div>
              </div>
              {bulkResult.errors?.length > 0 && (
                <pre className="xs">{JSON.stringify(bulkResult.errors, null, 1)}</pre>
              )}
              {bulkResult.invalid?.length > 0 && (
                <p className="muted xs">ผิดรูปแบบ (ตัวอย่าง): {bulkResult.invalid.join(', ')}</p>
              )}
            </section>
          )}

          {(mode === 'db' || mode === 'segment' || mode === 'push' || mode === 'broadcast') && (
            <section className="card">
              <div className="row spread">
                <button className="sm" onClick={doPreview}>ดูรายชื่อผู้รับ</button>
                {preview && <span className="sm"><b>{preview.count.toLocaleString()}</b> คน</span>}
              </div>
              {preview?.sample?.length > 0 && (
                <div className="recip-sample">
                  {preview.sample.map((u) => (
                    <div key={u.line_user_id} className="recip-chip" title={u.line_user_id}>
                      {u.picture_url && <img src={u.picture_url} alt="" />}
                      {u.display_name || u.line_user_id.slice(0, 8)}
                    </div>
                  ))}
                  {preview.count > preview.sample.length && <span className="muted xs">…อีก {(preview.count - preview.sample.length).toLocaleString()} คน</span>}
                </div>
              )}
            </section>
          )}

          {ncProgress && (
            <section className="card">
              <b className="sm">Narrowcast progress</b>
              <pre className="xs">{JSON.stringify(ncProgress, null, 1)}</pre>
              <button className="xs" onClick={async () => {
                try { setNcProgress({ ...await api.get(`/message/narrowcast/progress?requestId=${ncProgress.requestId}`), requestId: ncProgress.requestId }) } catch (e) { t.err(e.message) }
              }}>รีเฟรช</button>
            </section>
          )}

          <div className="row">
            <button className="sm" onClick={doValidate} disabled={busy}>ตรวจรูปแบบ</button>
            <button className="sm" onClick={sendTest} disabled={busy}>ส่งหาตัวเอง (ทดสอบ)</button>
            <button className="primary" onClick={send} disabled={busy}>{busy && <InlineSpinner />}ส่งจริง → {targetLabel}</button>
          </div>

          <section className="card" style={{ marginTop: 16 }}>
            <h3>ตั้งเวลาส่ง (Broadcast)</h3>
            <div className="row wrap">
              <input type="datetime-local" value={schedAt} onChange={(e) => setSchedAt(e.target.value)} />
              <button className="sm" onClick={doSchedule} disabled={busy}>ตั้งเวลา</button>
            </div>
            {scheduled.filter((j) => j.status === 'pending').length > 0 && (
              <table style={{ marginTop: 10 }}>
                <thead><tr><th>เวลา</th><th>ชนิด</th><th></th></tr></thead>
                <tbody>
                  {scheduled.filter((j) => j.status === 'pending').map((j) => (
                    <tr key={j.id}>
                      <td className="sm">{new Date(j.run_at).toLocaleString('th-TH')}</td>
                      <td>{j.kind}</td>
                      <td><button className="xs danger" onClick={() => api.cancelScheduled(j.id).then(loadScheduled)}>ยกเลิก</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="muted xs">ระบบเช็คทุก 5 นาที — เวลาส่งจริงอาจคลาดเคลื่อน ≤ 5 นาที</p>
          </section>
        </div>

        {/* ---------- ขวา: พรีวิว ---------- */}
        <div className="preview-pane">
          <div className="phone">
            <div className="phone-head">พรีวิว</div>
            <div className="phone-body">
              {messages.map((m, i) => (
                <MessagePreview key={i} msg={m} />
              ))}
            </div>
          </div>
          <p className="muted xs">* พรีวิวเป็นการประมาณ — สติกเกอร์/รูป/Flex บางส่วนอาจต่างจากใน LINE จริงเล็กน้อย</p>
        </div>
      </div>

      <section className="card">
        <h3>ประวัติการส่ง</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>ชนิด</th><th>ปลายทาง</th><th>ข้อความ</th><th>สถานะ</th><th>เวลา</th><th></th></tr></thead>
            <tbody>
              {history.map((b) => (
                <tr key={b.id}>
                  <td>{b.kind}</td>
                  <td>{b.target_count?.toLocaleString() ?? '–'}</td>
                  <td className="muted xs">{(b.messages || []).map((m) => m.type).join(', ')}</td>
                  <td><span className={`chip ${b.status}`}>{b.status}</span></td>
                  <td className="muted sm">{new Date(b.created_at).toLocaleString('th-TH')}</td>
                  <td><button className="xs" onClick={() => resend(b)}>ใช้ซ้ำ</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {gallery && (
        <TemplateGallery
          onClose={() => setGallery(false)}
          onPick={(msgs) => { setMessages(msgs.slice(0, 5)); window.scrollTo(0, 0); t.ok('ใส่เทมเพลตแล้ว — แก้เนื้อหา/ลิงก์/รูปก่อนส่ง') }}
        />
      )}
    </div>
  )
}
