import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { SkeletonStats, SkeletonRows, InlineSpinner, Stat, useToast } from '../lib/ui.jsx'
import { CAT, nf, dtf, Card, TimeArea, BarList, Donut, Empty } from '../components/Charts.jsx'

export default function Behavior() {
  const t = useToast()
  const [range, setRange] = useState(30)
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  const load = (r = range) => {
    setD(null); setErr('')
    api.behaviorAnalytics(r).then(setD).catch((e) => setErr(e.message))
  }
  useEffect(() => { load(range) }, [range]) // eslint-disable-line

  if (err) return <p className="err">{err}</p>
  if (!d) return (
    <div>
      <h1>วิเคราะห์พฤติกรรม</h1>
      <SkeletonStats />
      <div className="card"><SkeletonRows rows={6} cols={2} /></div>
    </div>
  )

  const totals = d.totals || {}
  const trendData = (d.trend || []).map((r) => ({ day: r.day, follow: r.follow, unfollow: -r.unfollow, unblock: r.unblock }))
  const topMenu = d.by_rich_menu?.[0]
  const topTag = (d.by_tag || []).find((x) => x.tag !== '(ไม่มีแท็ก)')
  const topBucket = [...(d.time_to_unfollow || [])].sort((a, b) => b.count - a.count)[0]
  const worstBroadcast = d.broadcast_impact?.[0]

  return (
    <div className="dash">
      <div className="row spread wrap" style={{ alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>วิเคราะห์พฤติกรรม</h1>
        <div className="row wrap" style={{ gap: 6 }}>
          {[7, 14, 30, 60, 90].map((r) => (
            <button key={r} className={range === r ? 'sm primary' : 'sm'} onClick={() => setRange(r)}>{r} วัน</button>
          ))}
          <button className="sm" onClick={() => load()} title="รีเฟรช">↻</button>
        </div>
      </div>
      <p className="muted xs" style={{ margin: '2px 0 8px' }}>เน้นวิเคราะห์การเลิกติดตาม (unfollow) — ใคร เมื่อไหร่ อยู่เมนูไหน เกี่ยวกับ broadcast ล่าสุดไหม</p>

      <div className="grid stats">
        <Stat label="เพิ่มเพื่อน" value={nf(totals.follow)} />
        <Stat label="เลิกติดตาม" value={nf(totals.unfollow)} sub={totals.churn_rate_pct != null ? `${totals.churn_rate_pct}% ของเพิ่มเพื่อน` : ''} />
        <Stat label="สุทธิ" value={(totals.net > 0 ? '+' : '') + nf(totals.net)} />
        <Stat label="เลิก-กลับมาซ้ำ" value={nf(totals.repeat_unfollowers)} sub="เคยบล็อกมาแล้ว >1 ครั้ง" />
      </div>

      {/* ---- สรุปเป็นภาษาคน ---- */}
      {totals.unfollow > 0 && (
        <Card title="🔎 สรุปสิ่งที่น่าจะเป็นสาเหตุ">
          <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
            {topBucket && <li>คนที่เลิกติดตามส่วนใหญ่ (<b>{topBucket.count}</b> คน) ทำ<b>{topBucket.bucket}</b> — {
              topBucket.bucket.includes('1 ชม.') || topBucket.bucket.includes('1 วัน')
                ? 'สัญญาณไม่ดี: คนใหม่หนีเร็วมาก น่าจะมีอะไรในข้อความต้อนรับ/เมนูแรกที่ทำให้อึดอัด'
                : 'เป็นคนที่ติดตามมานานแล้วค่อยเลิก อาจเป็นการเคลียร์บัญชีทั่วไปมากกว่าปัญหาเฉพาะจุด'
            }</li>}
            {topMenu && topMenu.menu !== '(ไม่มีเมนู)' && (
              <li>เมนูที่คนถืออยู่ตอนเลิกติดตามมากที่สุดคือ <b>{topMenu.menu}</b> ({topMenu.count} คน) — ลองดูว่าข้อความ/ปุ่มในเมนูนี้มีอะไรผลักลูกค้าหรือไม่</li>
            )}
            {topTag && <li>ในกลุ่มที่เลิกติดตาม แท็กที่เจอบ่อยสุดคือ <b>{topTag.tag}</b> ({topTag.count} คน)</li>}
            {worstBroadcast && (
              <li>
                <b>น่าสงสัยที่สุด:</b> หลังส่ง broadcast #{worstBroadcast.broadcast_id} ({worstBroadcast.kind}) เมื่อ {dtf(worstBroadcast.sent_at)}
                {' '}มีคนเลิกติดตามภายใน 72 ชม. ถึง <b>{worstBroadcast.unfollowed_within_72h} คน</b>
                {worstBroadcast.pct != null && ` (${worstBroadcast.pct}% ของที่ส่งไป)`} — ควรเปิดดูเนื้อหาแคมเปญนั้นว่ามีอะไรทำให้ลูกค้าไม่พอใจ (เช่น ลิงก์พัง/ข้อความรบกวน)
              </li>
            )}
          </ul>
        </Card>
      )}

      <div className="grid two">
        <Card title="เทรนด์เพิ่มเพื่อน / เลิกติดตาม" sub={`${d.days} วันล่าสุด`}>
          <TimeArea data={trendData} keys={[
            { k: 'follow', name: 'เพิ่มเพื่อน', color: CAT[0] },
            { k: 'unfollow', name: 'เลิกติดตาม', color: '#e5484d' },
          ]} />
        </Card>
        <Card title="ระยะเวลาก่อนเลิกติดตาม" sub="นับจากวันที่เพิ่มเพื่อนครั้งแรก">
          <Donut rows={d.time_to_unfollow} nameKey="bucket" valueKey="count" />
        </Card>
      </div>

      <div className="grid two">
        <Card title="เมนูที่ถืออยู่ตอนเลิกติดตาม" sub="Top 10">
          <BarList rows={d.by_rich_menu} labelKey="menu" valueKey="count" color={CAT} />
        </Card>
        <Card title="สถานะ (pipeline) ตอนเลิกติดตาม">
          <BarList rows={d.by_stage} labelKey="stage" valueKey="count" color={CAT[2]} />
        </Card>
      </div>

      <div className="grid two">
        <Card title="แท็กที่เจอบ่อยในกลุ่มที่เลิกติดตาม" sub="Top 15">
          <BarList rows={d.by_tag} labelKey="tag" valueKey="count" color={CAT[4]} />
        </Card>
        <Card title="แหล่งที่มา (source)">
          <BarList rows={d.by_source} labelKey="source" valueKey="count" color={CAT[3]} />
        </Card>
      </div>

      <Card title="ผลกระทบจาก Broadcast" sub="นับคนที่เลิกติดตามภายใน 72 ชม. หลังส่งแต่ละแคมเปญ">
        {!d.broadcast_impact?.length ? <Empty /> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>ส่งเมื่อ</th><th>ชนิด</th><th>ส่งถึง</th><th>เลิกติดตามใน 72ชม.</th><th>%</th></tr></thead>
              <tbody>
                {d.broadcast_impact.map((b) => (
                  <tr key={b.broadcast_id}>
                    <td className="muted sm">{dtf(b.sent_at)}</td>
                    <td>{b.kind}</td>
                    <td>{nf(b.target_count)}</td>
                    <td><b className={b.unfollowed_within_72h >= 10 ? 'err' : ''}>{b.unfollowed_within_72h}</b></td>
                    <td className="muted">{b.pct != null ? `${b.pct}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="ตัวอย่างล่าสุด: ข้อความก่อนเลิกติดตาม" sub="20 คนล่าสุดที่เลิกติดตาม">
        {!d.recent_samples?.length ? <Empty /> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>userId</th><th>เลิกติดตามเมื่อ</th><th>เมนู</th><th>แท็ก</th><th>ข้อความล่าสุดก่อนเลิก</th></tr></thead>
              <tbody>
                {d.recent_samples.map((s) => (
                  <tr key={s.line_user_id + s.unfollowed_at}>
                    <td className="mono xs">{s.line_user_id.slice(0, 10)}…</td>
                    <td className="muted sm">{dtf(s.unfollowed_at)}</td>
                    <td className="muted xs">{s.rich_menu || '—'}</td>
                    <td className="row wrap" style={{ gap: 3 }}>
                      {(s.tags || []).map((tg) => <span key={tg} className="chip xs muted">{tg}</span>)}
                    </td>
                    <td className="muted xs">
                      {!s.last_messages?.length ? '(ไม่มีข้อความ)' : s.last_messages.map((m, i) => (
                        <div key={i}>{m.dir === 'in' ? '👤 ' : '🤖 '}{m.text}</div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
