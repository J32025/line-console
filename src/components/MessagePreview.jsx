import FlexPreview from './FlexPreview.jsx'
import { detectKind } from '../lib/messageTypes.js'

function Bubble({ children, pad = true }) {
  return <div className={`ln-bubble ${pad ? '' : 'nopad'}`}>{children}</div>
}

function Actions({ actions = [] }) {
  return (
    <div className="ln-actions">
      {actions.map((a, i) => <div key={i} className="ln-act">{a.label || a.text || a.uri || '—'}</div>)}
    </div>
  )
}

export default function MessagePreview({ msg }) {
  const kind = detectKind(msg)

  if (kind === 'text')
    return <Bubble>{msg.text || <span className="muted">(ข้อความว่าง)</span>}</Bubble>

  if (kind === 'sticker')
    return (
      <Bubble pad={false}>
        <img className="ln-sticker" alt="sticker"
          src={`https://stickershop.line-scdn.net/stickershop/v1/sticker/${msg.stickerId}/android/sticker.png`}
          onError={(e) => { e.target.style.display = 'none' }} />
        <div className="muted xs" style={{ padding: 6 }}>sticker {msg.packageId}/{msg.stickerId}</div>
      </Bubble>
    )

  if (kind === 'image')
    return (
      <Bubble pad={false}>
        {msg.originalContentUrl
          ? <img className="ln-img" src={msg.previewImageUrl || msg.originalContentUrl} alt="" />
          : <div className="ln-placeholder">รูปภาพ (ใส่ URL)</div>}
      </Bubble>
    )

  if (kind === 'video')
    return (
      <Bubble pad={false}>
        {msg.previewImageUrl
          ? <div className="ln-video"><img className="ln-img" src={msg.previewImageUrl} alt="" /><span className="ln-play">▶</span></div>
          : <div className="ln-placeholder">วิดีโอ (ใส่ URL)</div>}
      </Bubble>
    )

  if (kind === 'audio')
    return <Bubble>🎵 เสียง · {Math.round((msg.duration || 0) / 1000)} วิ</Bubble>

  if (kind === 'location')
    return (
      <Bubble pad={false}>
        <div className="ln-map">📍</div>
        <div style={{ padding: 8 }}>
          <div><b>{msg.title || '(ไม่มีชื่อ)'}</b></div>
          <div className="muted xs">{msg.address}</div>
        </div>
      </Bubble>
    )

  if (kind === 'buttons') {
    const t = msg.template
    return (
      <Bubble pad={false}>
        {t.thumbnailImageUrl && <img className="ln-img" src={t.thumbnailImageUrl} alt="" />}
        <div style={{ padding: 10 }}>
          {t.title && <div><b>{t.title}</b></div>}
          <div className="sm">{t.text}</div>
        </div>
        <Actions actions={t.actions} />
      </Bubble>
    )
  }

  if (kind === 'confirm') {
    const t = msg.template
    return (
      <Bubble pad={false}>
        <div style={{ padding: 12 }} className="sm">{t.text}</div>
        <Actions actions={t.actions} />
      </Bubble>
    )
  }

  if (kind === 'carousel') {
    return (
      <div className="ln-carousel">
        {(msg.template.columns || []).map((c, i) => (
          <div key={i} className="ln-bubble nopad" style={{ minWidth: 200 }}>
            {c.thumbnailImageUrl && <img className="ln-img" src={c.thumbnailImageUrl} alt="" />}
            <div style={{ padding: 8 }}>
              {c.title && <div><b>{c.title}</b></div>}
              <div className="xs">{c.text}</div>
            </div>
            <Actions actions={c.actions} />
          </div>
        ))}
      </div>
    )
  }

  if (kind === 'flex')
    return <div className="ln-flexwrap"><FlexPreview contents={msg.contents} /></div>

  return <Bubble><pre className="xs" style={{ margin: 0, background: 'none', color: 'inherit' }}>{JSON.stringify(msg, null, 1)}</pre></Bubble>
}
