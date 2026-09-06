// ตัว render Flex แบบง่าย — รองรับ bubble/carousel + box/text/image/button/separator/icon
// พอให้เห็นหน้าตาคร่าว ๆ ก่อนส่ง (ไม่ครบทุก property ของ LINE)

const SIZE = { xxs: 10, xs: 11, sm: 12, md: 14, lg: 17, xl: 20, xxl: 24, '3xl': 28, '4xl': 34, '5xl': 40 }

function Node({ n }) {
  if (!n || typeof n !== 'object') return null
  switch (n.type) {
    case 'box': {
      const horiz = n.layout === 'horizontal' || n.layout === 'baseline'
      return (
        <div style={{
          display: 'flex', flexDirection: horiz ? 'row' : 'column',
          gap: gap(n.spacing), alignItems: horiz ? 'center' : 'stretch',
          padding: pad(n.paddingAll), backgroundColor: n.backgroundColor,
          borderRadius: n.cornerRadius ? 8 : undefined, flex: n.flex,
        }}>
          {(n.contents || []).map((c, i) => <Node key={i} n={c} />)}
        </div>
      )
    }
    case 'text':
      return (
        <span style={{
          fontSize: SIZE[n.size] || 14, fontWeight: n.weight === 'bold' ? 700 : 400,
          color: n.color || '#111', textAlign: n.align || 'left',
          whiteSpace: n.wrap ? 'pre-wrap' : 'nowrap', overflow: 'hidden',
          textOverflow: 'ellipsis', flex: n.flex, lineHeight: 1.4,
        }}>
          {n.text}
        </span>
      )
    case 'image':
      return (
        <img src={n.url} alt="" style={{
          width: n.size === 'full' ? '100%' : 64, borderRadius: 4,
          objectFit: n.aspectMode === 'cover' ? 'cover' : 'contain',
          aspectRatio: (n.aspectRatio || '1:1').replace(':', '/'),
        }} />
      )
    case 'button':
      return (
        <div style={{
          background: n.style === 'primary' ? (n.color || '#06c755') : n.style === 'secondary' ? '#eee' : 'transparent',
          color: n.style === 'primary' ? '#fff' : (n.color || '#06c755'),
          border: n.style === 'link' ? 'none' : '1px solid #ddd',
          borderRadius: 6, padding: '8px 10px', textAlign: 'center', fontSize: 13, fontWeight: 600,
        }}>
          {n.action?.label || 'ปุ่ม'}
        </div>
      )
    case 'separator':
      return <div style={{ borderTop: `1px solid ${n.color || '#eee'}`, margin: '4px 0' }} />
    case 'icon':
      return <img src={n.url} alt="" style={{ width: SIZE[n.size] || 16, height: SIZE[n.size] || 16 }} />
    case 'span':
      return <span style={{ fontSize: SIZE[n.size] || 14, color: n.color, fontWeight: n.weight === 'bold' ? 700 : 400 }}>{n.text}</span>
    default:
      return null
  }
}

const gap = (s) => ({ none: 0, xs: 2, sm: 4, md: 8, lg: 12, xl: 16, xxl: 20 }[s] ?? 4)
const pad = (s) => ({ none: 0, xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }[s] ?? (s ? 12 : 0))

function Bubble({ b }) {
  return (
    <div style={{
      width: b.size === 'nano' ? 120 : b.size === 'micro' ? 160 : b.size === 'kilo' ? 240 : b.size === 'giga' ? 320 : 260,
      background: '#fff', borderRadius: 12, overflow: 'hidden', border: '1px solid #e5e7eb', flexShrink: 0,
    }}>
      {b.hero && <Node n={b.hero} />}
      {b.header && <div style={{ padding: 12, borderBottom: '1px solid #f0f0f0' }}><Node n={b.header} /></div>}
      {b.body && <div style={{ padding: 12 }}><Node n={b.body} /></div>}
      {b.footer && <div style={{ padding: 12, borderTop: '1px solid #f0f0f0', display: 'flex', flexDirection: 'column', gap: 6 }}><Node n={b.footer} /></div>}
    </div>
  )
}

export default function FlexPreview({ contents }) {
  if (!contents) return <div className="muted xs">ไม่มีเนื้อหา</div>
  try {
    if (contents.type === 'carousel') {
      return (
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 6 }}>
          {(contents.contents || []).map((b, i) => <Bubble key={i} b={b} />)}
        </div>
      )
    }
    return <Bubble b={contents} />
  } catch {
    return <div className="err xs">Flex JSON ไม่ถูกต้อง</div>
  }
}
