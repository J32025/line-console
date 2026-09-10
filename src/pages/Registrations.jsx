import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Spinner, InlineSpinner, Stat, useToast } from '../lib/ui.jsx'

const nf = (n) => (n == null ? '–' : Number(n).toLocaleString('th-TH'))
const baht = (n) => (n == null ? '–' : '฿' + Number(n).toLocaleString('th-TH'))

export default function Registrations() {
  const t = useToast()
  const [sum, setSum] = useState(null)
  const [list, setList] = useState(null)
  const [total, setTotal] = useState(0)
  const [f, setF] = useState({ course: '', paid: '', q: '' })
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState('')
  const [imp, setImp] = useState(null)     // import modal: {text}
  const [msg, setMsg] = useState(null)     // message modal: {text}
  const [detail, setDetail] = useState(null)
  const [view, setView] = useState('list')   // list | reconcile
  const [rec, setRec] = useState(null)
  const LIMIT = 100

  const loadSum = () => api.registrationsSummary().then(setSum).catch((e) => t.err(e.message))
  const load = (off = 0) => {
    setBusy('list')
    const qs = { limit: LIMIT, offset: off }
    if (f.course) qs.course = f.course
    if (f.paid) qs.paid = f.paid
    if (f.q.trim()) qs.q = f.q.trim()
    api.registrations(qs).then((d) => { setList(d.registrations); setTotal(d.total); setOffset(off) })
      .catch((e) => t.err(e.message)).finally(() => setBusy(''))
  }
  const loadRec = () => { setRec(null); api.reconcile().then(setRec).catch((e) => t.err(e.message)) }
  useEffect(() => { loadSum(); load(0) }, []) // eslint-disable-line
  useEffect(() => { load(0) }, [f.course, f.paid]) // eslint-disable-line
  useEffect(() => { if (view === 'reconcile' && !rec) loadRec() }, [view]) // eslint-disable-line

  const doImport = async () => {
    setBusy('import')
    try {
      const r = await api.importRegistrations({ text: imp.text })
      t.ok(`นำเข้า ${r.valid} รายการ · tag ${r.users_tagged} คน`)
      setImp(null); loadSum(); load(0)
    } catch (e) { t.err(e.message) } finally { setBusy('') }
  }
  const sendMsg = async () => {
    setBusy('msg')
    try {
      const r = await api.messageRegistrations({ course: f.course || undefined, paid: f.paid || undefined,
        messages: [{ type: 'text', text: msg.text }] })
      t.ok(`ส่งแล้ว ${r.sent} คน${r.failed ? ` (พลาด ${r.failed})` : ''}`)
      setMsg(null)
    } catch (e) { t.err(e.message) } finally { setBusy('') }
  }
  const togglePaid = async (r) => {
    try {
      await api.updateRegistration(r.id, { paid: !r.paid })
      setList((l) => l.map((x) => x.id === r.id ? { ...x, paid: !x.paid } : x))
      loadSum()
    } catch (e) { t.err(e.message) }
  }

  return (
    <div>
      <div className="row spread wrap" style={{ alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>ผู้ลงทะเบียนเรียน</h1>
        <div className="row">
          <button className="sm" disabled={busy === 'retag'} onClick={async () => {
            setBusy('retag')
            try { const r = await api.retagRegistrations(); t.ok(`tag แล้ว ${r.users_tagged} คน`); loadSum() }
            catch (e) { t.err(e.message) } finally { setBusy('') }
          }}>{busy === 'retag' && <InlineSpinner />}ซิงค์ tag</button>
          <button className="sm primary" onClick={() => setImp({ text: '' })}>+ นำเข้ารายชื่อ</button>
        </div>
      </div>

      <div className="dash-nav" style={{ position: 'static', border: 0, marginBottom: 10 }}>
        <button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>รายชื่อ</button>
        <button className={view === 'reconcile' ? 'active' : ''} onClick={() => setView('reconcile')}>กระทบยอด</button>
      </div>

      {view === 'reconcile' && <ReconcileView rec={rec} reload={loadRec} onMarked={() => { loadRec(); loadSum(); }} />}

      {view === 'list' && (!sum ? <Spinner /> : (
        <>
          <div className="grid stats">
            <Stat label="ลงทะเบียนทั้งหมด" value={nf(sum.total)} sub={`${nf(sum.people)} คน`} />
            <Stat label="จ่ายแล้ว" value={nf(sum.paid)} sub={`ค้างจ่าย ${nf(sum.total - sum.paid)}`} />
            {(sum.by_course || []).slice(0, 4).map((c) => (
              <Stat key={c.course} label={c.course} value={nf(c.count)} sub={`จ่าย ${nf(c.paid)} · ค้าง ${nf(c.unpaid)}`} />
            ))}
          </div>

          <section className="card">
            <div className="row wrap" style={{ gap: 6, alignItems: 'center' }}>
              <select value={f.course} onChange={(e) => setF({ ...f, course: e.target.value })}>
                <option value="">ทุกหลักสูตร</option>
                {(sum.by_course || []).map((c) => <option key={c.course} value={c.course}>{c.course}</option>)}
              </select>
              <select value={f.paid} onChange={(e) => setF({ ...f, paid: e.target.value })}>
                <option value="">จ่าย/ค้าง ทั้งหมด</option>
                <option value="true">จ่ายแล้ว</option>
                <option value="false">ค้างจ่าย</option>
              </select>
              <input placeholder="ค้นชื่อ/เบอร์/อีเมล/สังกัด" value={f.q}
                     onChange={(e) => setF({ ...f, q: e.target.value })}
                     onKeyDown={(e) => e.key === 'Enter' && load(0)} style={{ minWidth: 200 }} />
              <button className="sm" onClick={() => load(0)}>ค้นหา</button>
              <button className="sm" onClick={() => setMsg({ text: '' })}>✉️ ส่งข้อความกลุ่มนี้ ({total})</button>
            </div>
          </section>

          <section className="card">
            {!list || busy === 'list' ? <Spinner /> : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>ชื่อ</th><th>หลักสูตร</th><th>สังกัด</th><th>เบอร์</th><th>จ่าย</th><th>สลิป</th><th></th></tr>
                  </thead>
                  <tbody>
                    {list.map((r) => (
                      <tr key={r.id}>
                        <td>{r.name || <span className="muted mono xs">{(r.line_user_id || '').slice(0, 10)}</span>}</td>
                        <td><span className="chip">{r.course || '?'}</span></td>
                        <td className="sm ellipsis" style={{ maxWidth: 180 }}>{r.org || '–'}</td>
                        <td className="sm">{r.tel || '–'}</td>
                        <td>
                          <button className={`xs ${r.paid ? 'primary' : ''}`} onClick={() => togglePaid(r)}>
                            {r.paid ? '✓ จ่ายแล้ว' : 'ค้างจ่าย'}
                          </button>
                        </td>
                        <td>{r.slip_url ? <a href={r.slip_url} target="_blank" rel="noreferrer">ดู</a> : '–'}</td>
                        <td><button className="xs" onClick={() => setDetail(r.id)}>รายละเอียด</button></td>
                      </tr>
                    ))}
                    {!list.length && <tr><td colSpan={7} className="muted center">ไม่มีข้อมูล</td></tr>}
                  </tbody>
                </table>
                {list.length < total && (
                  <div className="row center" style={{ marginTop: 10 }}>
                    <button className="sm" onClick={() => load(offset + LIMIT)}>
                      โหลดเพิ่ม ({list.length}/{total})
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>
        </>
      ))}

      {imp && (
        <div className="modal-bg" onClick={() => setImp(null)}>
          <div className="modal" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>นำเข้ารายชื่อลงทะเบียน</h3><button className="xs" onClick={() => setImp(null)}>✕</button></div>
            <p className="muted xs">
              เปิดไฟล์ <code>ลงทะเบียนแล้ว.txt</code> (หรือ Google Sheet) → เลือกทั้งหมด (รวมหัวตาราง) → คัดลอก → วางที่นี่
              <br />ระบบจับคอลัมน์: UID, NAME, TEL, สังกัด, หลักสูตร, EMAIL, FILE, จ่าย · upsert ตาม (UID + หลักสูตร) · tag คอร์ส + "ลงทะเบียน" ให้ line_users · รันซ้ำได้
            </p>
            <textarea rows={10} value={imp.text} onChange={(e) => setImp({ text: e.target.value })}
                      placeholder="TIMESTAMP<tab>REGID<tab>UID<tab>NAME ..." style={{ fontFamily: 'monospace', fontSize: 11 }} />
            <button className="primary" disabled={busy === 'import' || !imp.text.trim()} onClick={doImport}>
              {busy === 'import' && <InlineSpinner />}นำเข้า
            </button>
          </div>
        </div>
      )}

      {msg && (
        <div className="modal-bg" onClick={() => setMsg(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="row spread"><h3>ส่งข้อความ</h3><button className="xs" onClick={() => setMsg(null)}>✕</button></div>
            <p className="muted xs">
              ส่งหา: {f.course || 'ทุกหลักสูตร'} · {f.paid === 'true' ? 'จ่ายแล้ว' : f.paid === 'false' ? 'ค้างจ่าย' : 'จ่าย/ค้าง ทั้งหมด'} — รวม {total} คน (multicast)
            </p>
            <textarea rows={5} value={msg.text} onChange={(e) => setMsg({ text: e.target.value })} placeholder="ข้อความ…" />
            <button className="primary" disabled={busy === 'msg' || !msg.text.trim()} onClick={sendMsg}>
              {busy === 'msg' && <InlineSpinner />}ส่ง
            </button>
          </div>
        </div>
      )}

      {detail && <RegDetail id={detail} onClose={() => setDetail(null)} onSaved={() => { load(offset); loadSum() }} />}
    </div>
  )
}

function RegDetail({ id, onClose, onSaved }) {
  const t = useToast()
  const [d, setD] = useState(null)
  const [note, setNote] = useState('')
  useEffect(() => {
    api.registration(id).then((r) => { setD(r); setNote(r.registration.note || '') }).catch((e) => t.err(e.message))
  }, [id]) // eslint-disable-line

  const save = async (patch) => {
    try { await api.updateRegistration(id, patch); t.ok('บันทึกแล้ว'); onSaved() } catch (e) { t.err(e.message) }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="row spread"><h3>รายละเอียดผู้ลงทะเบียน</h3><button className="xs" onClick={onClose}>✕</button></div>
        {!d ? <Spinner /> : (
          <>
            <table className="kv"><tbody>
              <tr><th>ชื่อ</th><td>{d.registration.name || '–'}</td></tr>
              <tr><th>หลักสูตร</th><td><span className="chip">{d.registration.course}</span> <span className="muted xs">{d.registration.course_raw}</span></td></tr>
              <tr><th>สังกัด</th><td>{d.registration.org || '–'}</td></tr>
              <tr><th>เบอร์ / อีเมล</th><td>{d.registration.tel || '–'} · {d.registration.email || '–'}</td></tr>
              <tr><th>REGID</th><td className="mono xs">{d.registration.reg_id || '–'}</td></tr>
              <tr><th>LINE</th><td>{d.user?.display_name || <span className="mono xs">{d.registration.line_user_id}</span>} {d.user && !d.user.is_following && <span className="chip failed">unfollow</span>}</td></tr>
              <tr><th>ลงเมื่อ</th><td className="sm">{d.registration.form_ts || '–'}</td></tr>
              <tr><th>สลิป (ฟอร์ม)</th><td>{d.registration.slip_url ? <a href={d.registration.slip_url} target="_blank" rel="noreferrer">เปิด Drive</a> : '–'}</td></tr>
            </tbody></table>

            <div className="row wrap" style={{ margin: '8px 0' }}>
              <button className={d.registration.paid ? 'sm primary' : 'sm'} onClick={() => save({ paid: !d.registration.paid })}>
                {d.registration.paid ? '✓ จ่ายแล้ว' : 'ทำเครื่องหมายจ่ายแล้ว'}
              </button>
              <button className={d.registration.approved ? 'sm primary' : 'sm'} onClick={() => save({ approved: !d.registration.approved })}>
                {d.registration.approved ? '✓ อนุมัติ' : 'อนุมัติ'}
              </button>
            </div>

            <label className="sm">โน้ต</label>
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="sm primary" onClick={() => save({ note })}>บันทึกโน้ต</button>

            {d.slips?.length > 0 && (
              <>
                <h4 className="sm" style={{ marginTop: 12 }}>สลิปในระบบ ({d.slips.length})</h4>
                <ul className="loglist">
                  {d.slips.map((s) => (
                    <li key={s.id}>
                      <span className={`chip ${s.status === 'verified' ? 'ok' : s.status === 'rejected' ? 'failed' : ''}`}>{s.status}</span>
                      {s.amount && <span>{Number(s.amount).toLocaleString()} บาท</span>}
                      {s.expected_course && <span className="muted xs">{s.expected_course}</span>}
                      <span className="muted xs">{new Date(s.created_at).toLocaleDateString('th-TH')}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {d.other_registrations?.length > 0 && (
              <p className="muted xs">คอร์สอื่นของคนนี้: {d.other_registrations.map((o) => `${o.course}${o.paid ? '✓' : ''}`).join(', ')}</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ReconcileView({ rec, reload, onMarked }) {
  const t = useToast()
  const [busy, setBusy] = useState(false)
  if (!rec) return <Spinner />
  const T = rec.totals
  const I = rec.issues

  const markAll = async () => {
    const ids = (I.paid_not_marked || []).map((x) => x.id)
    if (!ids.length) return
    setBusy(true)
    try { const r = await api.reconcileMarkPaid(ids); t.ok(`mark จ่ายแล้ว ${r.marked} รายการ`); onMarked() }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="grid stats">
        <Stat label="ลงทะเบียน" value={nf(T.registered)} />
        <Stat label="mark จ่ายแล้ว" value={nf(T.paid_marked)} sub={`ค้าง ${nf(T.registered - T.paid_marked)}`} />
        <Stat label="สลิปยืนยัน (EasySlip)" value={nf(T.slip_verified)} />
        <Stat label="ยอดเงินรับจริง" value={baht(T.revenue)} sub={`คาด ${baht(T.expected_revenue)}`} />
      </div>

      <section className="card">
        <div className="row spread"><h3>แยกตามหลักสูตร</h3><button className="xs" onClick={reload}>รีเฟรช</button></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>หลักสูตร</th><th>ลงทะเบียน</th><th>จ่ายแล้ว</th><th>สลิปยืนยัน</th><th>รับจริง</th><th>คาด</th><th>ส่วนต่าง</th></tr></thead>
            <tbody>
              {rec.by_course.map((c) => (
                <tr key={c.course}>
                  <td><b>{c.course}</b></td><td>{nf(c.registered)}</td>
                  <td>{nf(c.paid)}</td><td>{nf(c.slip_verified)}</td>
                  <td>{baht(c.revenue)}</td><td className="muted">{baht(c.expected_revenue)}</td>
                  <td style={{ color: c.revenue >= c.expected_revenue ? 'var(--primary-d)' : 'var(--danger)' }}>
                    {baht(c.revenue - c.expected_revenue)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>🟢 จ่ายแล้ว (สลิปยืนยัน) แต่ทะเบียนยังไม่ mark — {nf(I.paid_not_marked_count)}</h3>
          {I.paid_not_marked?.length > 0 && (
            <button className="sm primary" disabled={busy} onClick={markAll}>
              {busy && <InlineSpinner />}mark จ่ายแล้วทั้งหมด
            </button>
          )}
        </div>
        <IssueTable rows={I.paid_not_marked} extra="slip_amount" />
      </section>

      <section className="card">
        <div className="row spread">
          <h3>🟠 ลงทะเบียนแล้ว ยังไม่จ่าย (ไม่มีสลิป) — {nf(I.unpaid_count)}</h3>
          {I.unpaid?.length > 0 && (
            <button className="sm" disabled={busy} onClick={async () => {
              if (!confirm(`สร้างงาน "ตามจ่าย" ${I.unpaid.length} รายการ?`)) return
              setBusy(true)
              try {
                await api.createTasksBulk({
                  title: 'ตามชำระเงิน', tag: 'จ่ายเงิน',
                  dueAt: new Date(Date.now() + 2 * 864e5).toISOString(),
                  userIds: I.unpaid.map((x) => x.line_user_id),
                })
                t.ok(`สร้างงาน ${I.unpaid.length} รายการ (ครบกำหนด 2 วัน)`)
              } catch (e) { t.err(e.message) } finally { setBusy(false) }
            }}>สร้างงานตามจ่ายทั้งหมด</button>
          )}
        </div>
        <p className="muted xs">tag `ลงทะเบียน` + คอร์ส แล้ว — หรือไปหน้า "ส่งข้อความ" เลือก tag คอร์ส เพื่อทวงชำระ</p>
        <IssueTable rows={I.unpaid} />
      </section>

      <section className="card">
        <h3>🔴 ส่งสลิปยืนยันแล้ว แต่ไม่มีทะเบียนคอร์สนั้น — {nf(I.slip_no_reg_count)}</h3>
        <p className="muted xs">คนพวกนี้จ่ายเงินแล้วแต่ยังไม่ได้กรอกฟอร์มลงทะเบียน — ติดต่อให้ลงทะเบียน</p>
        <div className="table-scroll">
          <table>
            <thead><tr><th>ชื่อ / userId</th><th>คอร์ส (จากสลิป)</th><th>ยอด</th><th>เหตุผล</th></tr></thead>
            <tbody>
              {(I.slip_no_reg || []).map((x) => (
                <tr key={x.id}>
                  <td>{x.name || <span className="mono xs">{x.line_user_id.slice(0, 12)}</span>}</td>
                  <td>{x.course || '–'}</td><td>{baht(x.amount)}</td>
                  <td className="muted sm">{x.reason}</td>
                </tr>
              ))}
              {!I.slip_no_reg?.length && <tr><td colSpan={4} className="muted">ไม่มี — ทุกสลิปตรงกับทะเบียน 👍</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function IssueTable({ rows, extra }) {
  if (!rows?.length) return <p className="muted sm">ไม่มี 👍</p>
  return (
    <div className="table-scroll">
      <table>
        <thead><tr><th>ชื่อ</th><th>หลักสูตร</th><th>เบอร์</th><th>สังกัด</th>{extra && <th>สลิป</th>}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name || <span className="mono xs">{(r.line_user_id || '').slice(0, 10)}</span>}</td>
              <td><span className="chip">{r.course}</span></td>
              <td className="sm">{r.tel || '–'}</td>
              <td className="sm ellipsis" style={{ maxWidth: 160 }}>{r.org || '–'}</td>
              {extra && <td>{baht(r[extra])}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
