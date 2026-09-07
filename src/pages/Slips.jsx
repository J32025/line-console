import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { SkeletonCards, InlineSpinner, useToast } from '../lib/ui.jsx'

const TABS = [['new', 'ใหม่'], ['verified', 'ผ่าน'], ['rejected', 'ไม่ผ่าน'], ['', 'ทั้งหมด']]

export default function Slips() {
  const t = useToast()
  const [list, setList] = useState(null)
  const [tab, setTab] = useState('new')
  const [newCount, setNewCount] = useState(0)
  const [zoom, setZoom] = useState(null)
  const [busy, setBusy] = useState(0)

  const load = () => api.slips(tab).then((d) => { setList(d.slips); setNewCount(d.new_count) }).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [tab]) // eslint-disable-line
  useEffect(() => { const i = setInterval(load, 20000); return () => clearInterval(i) }, [tab]) // eslint-disable-line

  const act = async (s, status, replyUser) => {
    setBusy(s.id)
    try {
      await api.updateSlip(s.id, { status, replyUser })
      t.ok(status === 'verified' ? 'ยืนยันแล้ว' : 'ปฏิเสธแล้ว')
      load()
    } catch (e) { t.err(e.message) } finally { setBusy(0) }
  }

  return (
    <div>
      <h1>สลิปโอนเงิน {newCount > 0 && <span className="chip failed">{newCount} ใหม่</span>}</h1>
      <div className="row">
        {TABS.map(([v, l]) => <button key={v} className={tab === v ? 'sm primary' : 'sm'} onClick={() => setTab(v)}>{l}</button>)}
        <button className="sm" onClick={load}>รีเฟรช</button>
      </div>

      {!list ? <SkeletonCards count={6} /> : list.length === 0 ? (
        <p className="muted card center">ไม่มีสลิป{tab === 'new' ? 'ใหม่' : ''}</p>
      ) : (
        <div className="slip-grid">
          {list.map((s) => (
            <div key={s.id} className={`slip-card ${s.status}`}>
              {s.media_url
                ? <img src={s.media_url} alt="slip" onClick={() => setZoom(s.media_url)} />
                : <div className="slip-noimg">โหลดรูปไม่ได้</div>}
              <div className="slip-body">
                <div className="row spread">
                  <b className="sm ellipsis">{s.user?.display_name || s.line_user_id.slice(0, 10)}</b>
                  <span className={`chip ${s.status === 'verified' ? 'ok' : s.status === 'rejected' ? 'failed' : ''}`}>{s.status}</span>
                </div>
                {s.amount && <div className="sm">💰 {Number(s.amount).toLocaleString()} บาท {s.bank && `· ${s.bank}`}</div>}
                {s.ref && <div className="muted xs">ref: {s.ref}</div>}
                <div className="muted xs">{new Date(s.created_at).toLocaleString('th-TH')}</div>
                {s.status === 'new' && (
                  <div className="row" style={{ marginTop: 6 }}>
                    <button className="xs primary" disabled={busy === s.id} onClick={() => act(s, 'verified', true)}>
                      {busy === s.id ? <InlineSpinner /> : '✓'} ผ่าน + แจ้ง user
                    </button>
                    <button className="xs danger" disabled={busy === s.id} onClick={() => act(s, 'rejected', true)}>✕ ไม่ผ่าน</button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {zoom && (
        <div className="modal-bg" onClick={() => setZoom(null)}>
          <img src={zoom} alt="" style={{ maxWidth: '92vw', maxHeight: '92vh', borderRadius: 10 }} />
        </div>
      )}
    </div>
  )
}
