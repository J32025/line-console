// คลังเทมเพลตข้อความ — จัดหมวด, แต่ละอันคืน array ของ LINE message object (แก้ต่อได้)
// รูป placeholder ใช้ https://placehold.co (เปลี่ยนเป็น URL จริงก่อนส่ง)

const IMG = (w, h, txt = '') => `https://placehold.co/${w}x${h}?text=${encodeURIComponent(txt)}`
const GREEN = '#06c755'

// ---------- helpers ----------
const txt = (text, o = {}) => ({ type: 'text', text, wrap: true, ...o })
const btn = (label, uri, o = {}) => ({ type: 'button', style: 'primary', color: GREEN, action: { type: 'uri', label, uri: uri || 'https://example.com' }, ...o })
const linkbtn = (label, uri) => ({ type: 'button', style: 'link', action: { type: 'uri', label, uri: uri || 'https://example.com' } })
const sep = () => ({ type: 'separator' })
const kv = (k, v) => ({ type: 'box', layout: 'baseline', spacing: 'sm', contents: [
  { type: 'text', text: k, color: '#aaaaaa', size: 'sm', flex: 2 },
  { type: 'text', text: v, wrap: true, color: '#555555', size: 'sm', flex: 5 },
] })
const bubble = (b) => ({ type: 'bubble', ...b })
const flex = (altText, contents) => ({ type: 'flex', altText, contents })

// ==================================================================
export const GALLERY = [

  // ========== ทักทาย / ต้อนรับ ==========
  { cat: 'ทักทาย', name: 'ต้อนรับเพื่อนใหม่', desc: 'ข้อความ + สติกเกอร์',
    build: () => [
      txt('สวัสดีครับ 🙏 ยินดีต้อนรับเข้าสู่ทางการของเรา\nพิมพ์ "เมนู" เพื่อดูบริการทั้งหมดได้เลยครับ'),
      { type: 'sticker', packageId: '11537', stickerId: '52002734' },
    ] },
  { cat: 'ทักทาย', name: 'ต้อนรับ + ปุ่มเริ่มต้น', desc: 'Flex bubble ต้อนรับ',
    build: () => [flex('ยินดีต้อนรับ', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('ยินดีต้อนรับ! 👋', { weight: 'bold', size: 'xl' }),
        txt('ขอบคุณที่เพิ่มเราเป็นเพื่อน เริ่มต้นใช้งานได้เลย', { size: 'sm', color: '#666666' }),
      ] },
      footer: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        btn('ดูบริการทั้งหมด'), linkbtn('ติดต่อแอดมิน'),
      ] },
    }))] },
  { cat: 'ทักทาย', name: 'ทักทายตอนเช้า', desc: 'ข้อความสั้น',
    build: () => [txt('อรุณสวัสดิ์ครับ ☀️ ขอให้เป็นวันที่ดีนะครับ')] },
  { cat: 'ทักทาย', name: 'Quick Reply เมนูหลัก', desc: 'ข้อความ + ปุ่มลัด',
    build: () => [{ type: 'text', text: 'เลือกเมนูที่ต้องการได้เลยครับ', quickReply: { items: [
      { type: 'action', action: { type: 'message', label: 'สมัครเรียน', text: 'สมัครเรียน' } },
      { type: 'action', action: { type: 'message', label: 'ตารางเรียน', text: 'ตารางเรียน' } },
      { type: 'action', action: { type: 'message', label: 'ราคา', text: 'ราคา' } },
      { type: 'action', action: { type: 'message', label: 'ติดต่อแอดมิน', text: 'ติดต่อแอดมิน' } },
    ] } }] },

  // ========== ประกาศ / ข่าวสาร ==========
  { cat: 'ประกาศ', name: 'ประกาศทั่วไป', desc: 'Flex กล่องประกาศ',
    build: () => [flex('ประกาศ', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('📢 ประกาศ', { weight: 'bold', size: 'lg', color: GREEN }),
        sep(),
        txt('รายละเอียดประกาศ อธิบายเนื้อหาได้หลายบรรทัดตามต้องการ', { size: 'sm' }),
        { type: 'box', layout: 'vertical', margin: 'md', spacing: 'sm', contents: [
          kv('มีผลวันที่', '1 ต.ค. 2569'), kv('ผู้ประกาศ', 'ทีมงาน'),
        ] },
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('อ่านเพิ่มเติม')] },
    }))] },
  { cat: 'ประกาศ', name: 'ประกาศด่วน (สีแดง)', desc: 'เน้นความเร่งด่วน',
    build: () => [flex('ประกาศด่วน', bubble({
      body: { type: 'box', layout: 'vertical', backgroundColor: '#dc2626', paddingAll: 'lg', spacing: 'sm', contents: [
        txt('⚠️ ประกาศด่วน', { weight: 'bold', size: 'lg', color: '#ffffff' }),
        txt('เนื้อหาประกาศด่วนที่ต้องการให้ทุกคนทราบทันที', { size: 'sm', color: '#ffffff' }),
      ] },
    }))] },
  { cat: 'ประกาศ', name: 'ข่าวสาร/บทความ', desc: 'การ์ดข่าวมีรูป',
    build: () => [flex('ข่าวสาร', bubble({
      hero: { type: 'image', url: IMG(1024, 512, 'NEWS'), size: 'full', aspectRatio: '20:10', aspectMode: 'cover' },
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('หัวข้อข่าว', { weight: 'bold', size: 'lg' }),
        txt('สรุปเนื้อหาข่าวย่อ ๆ 2-3 บรรทัด อ่านต่อได้ที่ลิงก์ด้านล่าง', { size: 'sm', color: '#888888' }),
        { type: 'text', text: '7 ก.ย. 2569', size: 'xs', color: '#aaaaaa', margin: 'md' },
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [linkbtn('อ่านบทความเต็ม')] },
    }))] },
  { cat: 'ประกาศ', name: 'ตารางกิจกรรม/Timeline', desc: 'Flex ไทม์ไลน์',
    build: () => [flex('ตารางกิจกรรม', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('🗓️ ตารางกิจกรรมสัปดาห์นี้', { weight: 'bold', size: 'md' }),
        sep(),
        ...['จ. 09:00 — เปิดรับสมัคร', 'พ. 13:00 — ปฐมนิเทศ', 'ศ. 18:00 — ติวเข้ม', 'ส. 09:00 — สอบวัดระดับ'].map((t) =>
          ({ type: 'box', layout: 'horizontal', spacing: 'sm', contents: [
            { type: 'text', text: '●', color: GREEN, flex: 0, size: 'sm' },
            { type: 'text', text: t, size: 'sm', wrap: true, color: '#555555' },
          ] })),
      ] },
    }))] },

  // ========== โปรโมชัน / ส่วนลด ==========
  { cat: 'โปรโมชัน', name: 'คูปองส่วนลด %', desc: 'บับเบิลคูปองสีเขียว',
    build: () => [flex('คูปองส่วนลด', bubble({ size: 'kilo',
      body: { type: 'box', layout: 'vertical', backgroundColor: GREEN, paddingAll: 'xl', spacing: 'md', contents: [
        txt('ส่วนลดพิเศษ', { color: '#ffffff', size: 'sm' }),
        txt('50%', { color: '#ffffff', size: '5xl', weight: 'bold' }),
        txt('โค้ด SAVE50 · หมดเขต 31 ต.ค. 69', { color: '#ffffffcc', size: 'xs' }),
        { type: 'button', style: 'secondary', margin: 'md', action: { type: 'uri', label: 'ใช้คูปอง', uri: 'https://example.com' } },
      ] },
    }))] },
  { cat: 'โปรโมชัน', name: 'ดีลจำกัดเวลา (Countdown)', desc: 'เน้นความเร่งด่วน',
    build: () => [flex('ดีลจำกัดเวลา', bubble({
      hero: { type: 'image', url: IMG(1024, 400, 'FLASH SALE'), size: 'full', aspectRatio: '20:8', aspectMode: 'cover' },
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('⏰ FLASH SALE เหลือเวลาอีกไม่นาน!', { weight: 'bold', size: 'md', color: '#dc2626' }),
        txt('ลดสูงสุด 70% เฉพาะวันนี้เท่านั้น', { size: 'sm', color: '#666666' }),
        { type: 'box', layout: 'baseline', margin: 'md', contents: [
          txt('฿590', { weight: 'bold', size: 'xxl', flex: 0 }),
          txt('฿1,990', { size: 'sm', color: '#aaaaaa', decoration: 'line-through', margin: 'sm' }),
        ] },
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('ซื้อเลย')] },
    }))] },
  { cat: 'โปรโมชัน', name: 'แจกโค้ด (ข้อความ)', desc: 'ข้อความล้วน',
    build: () => [txt('🎁 รับโค้ดส่วนลด: WELCOME100\nลด 100 บาท เมื่อสมัครวันนี้\nใช้ได้ถึง 30 ก.ย. 69 เท่านั้น')] },
  { cat: 'โปรโมชัน', name: 'โปรโมชันหลายรายการ (Carousel)', desc: 'การ์ดสไลด์ 3 โปร',
    build: () => [flex('โปรโมชัน', { type: 'carousel', contents: [
      ['คอร์สติวเข้ม', '฿1,990', 'ลด 40%'],
      ['คอร์สออนไลน์', '฿990', 'ลด 50%'],
      ['แพ็กคู่', '฿2,490', 'ประหยัด ฿1,500'],
    ].map(([name, price, tag]) => bubble({ size: 'micro',
      hero: { type: 'image', url: IMG(300, 200, name), size: 'full', aspectRatio: '3:2', aspectMode: 'cover' },
      body: { type: 'box', layout: 'vertical', spacing: 'xs', contents: [
        txt(name, { weight: 'bold', size: 'sm' }),
        txt(price, { size: 'sm', color: GREEN, weight: 'bold' }),
        txt(tag, { size: 'xxs', color: '#dc2626' }),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [linkbtn('ดูโปร')] },
    })) })] },

  // ========== ขายสินค้า / คอร์ส ==========
  { cat: 'สินค้า/คอร์ส', name: 'การ์ดสินค้า (มาตรฐาน)', desc: 'รูป + ราคา + ปุ่ม',
    build: () => [flex('สินค้า', bubble({
      hero: { type: 'image', url: IMG(1024, 640, 'PRODUCT'), size: 'full', aspectRatio: '20:13', aspectMode: 'cover' },
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('ชื่อสินค้า / คอร์ส', { weight: 'bold', size: 'xl' }),
        { type: 'box', layout: 'baseline', contents: [
          { type: 'text', text: '★★★★☆', size: 'sm', color: '#f5a623', flex: 0 },
          txt('4.2 (128)', { size: 'xs', color: '#999999', margin: 'sm' }),
        ] },
        { type: 'box', layout: 'baseline', margin: 'md', contents: [
          txt('฿1,990', { weight: 'bold', size: 'lg', flex: 0 }),
          txt('฿2,990', { size: 'sm', color: '#aaaaaa', decoration: 'line-through', margin: 'sm' }),
        ] },
        txt('รายละเอียดสั้น ๆ เกี่ยวกับสินค้า/คอร์สนี้', { size: 'sm', color: '#666666', margin: 'sm' }),
      ] },
      footer: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [btn('สั่งซื้อ / สมัคร'), linkbtn('ดูรายละเอียด')] },
    }))] },
  { cat: 'สินค้า/คอร์ส', name: 'ตารางราคา (3 แพ็ก)', desc: 'เทียบราคา Carousel',
    build: () => [flex('แพ็กเกจ', { type: 'carousel', contents: [
      ['Basic', '฿990', ['เรียนออนไลน์', 'เอกสาร PDF', 'กลุ่มถาม-ตอบ']],
      ['Pro', '฿1,990', ['ทุกอย่างใน Basic', 'ติวสด 8 ครั้ง', 'ตรวจการบ้าน']],
      ['Premium', '฿3,490', ['ทุกอย่างใน Pro', 'ติวตัวต่อตัว 4 ครั้ง', 'รับประกันผล']],
    ].map(([name, price, feats], i) => bubble({ size: 'kilo',
      header: { type: 'box', layout: 'vertical', backgroundColor: i === 1 ? GREEN : '#f4f4f4', paddingAll: 'lg', contents: [
        txt(name, { weight: 'bold', size: 'lg', color: i === 1 ? '#ffffff' : '#333333' }),
        txt(price, { size: 'xl', weight: 'bold', color: i === 1 ? '#ffffff' : GREEN }),
      ] },
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: feats.map((f) =>
        ({ type: 'box', layout: 'baseline', spacing: 'sm', contents: [
          { type: 'text', text: '✓', color: GREEN, flex: 0, size: 'sm' },
          { type: 'text', text: f, size: 'sm', wrap: true, color: '#555555' },
        ] })) },
      footer: { type: 'box', layout: 'vertical', contents: [btn('เลือกแพ็กนี้')] },
    })) })] },
  { cat: 'สินค้า/คอร์ส', name: 'สินค้าหลายชิ้น (รายการ)', desc: 'Flex list มีรูปเล็ก',
    build: () => [flex('รายการสินค้า', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('สินค้าแนะนำ', { weight: 'bold', size: 'lg' }),
        ...[['หนังสือติว ม.6', '฿350'], ['ชุดข้อสอบเก่า', '฿250'], ['คอร์สสรุป', '฿990']].map(([n, p]) =>
          ({ type: 'box', layout: 'horizontal', spacing: 'md', contents: [
            { type: 'image', url: IMG(100, 100), size: 'sm', aspectMode: 'cover', flex: 0 },
            { type: 'box', layout: 'vertical', contents: [txt(n, { size: 'sm', weight: 'bold' }), txt(p, { size: 'sm', color: GREEN })] },
          ] })),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('ดูสินค้าทั้งหมด')] },
    }))] },

  // ========== อีเวนต์ / สัมมนา ==========
  { cat: 'อีเวนต์', name: 'บัตรเชิญงาน/สัมมนา', desc: 'Flex บัตรเชิญ',
    build: () => [flex('บัตรเชิญ', bubble({
      hero: { type: 'image', url: IMG(1024, 512, 'EVENT'), size: 'full', aspectRatio: '20:10', aspectMode: 'cover' },
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('ชื่องานสัมมนา', { weight: 'bold', size: 'xl' }),
        { type: 'box', layout: 'vertical', margin: 'md', spacing: 'sm', contents: [
          kv('📅 วันที่', '15 ต.ค. 2569'), kv('🕐 เวลา', '13:00 - 16:00 น.'),
          kv('📍 สถานที่', 'ห้องประชุม A / Zoom'), kv('💰 ค่าเข้า', 'ฟรี'),
        ] },
      ] },
      footer: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [btn('ลงทะเบียนเข้าร่วม'), linkbtn('เพิ่มลงปฏิทิน')] },
    }))] },
  { cat: 'อีเวนต์', name: 'แจ้งเตือนก่อนงาน', desc: 'ข้อความเตือน',
    build: () => [txt('🔔 เตือนความจำ: งานสัมมนาจะเริ่มพรุ่งนี้ 13:00 น.\nอย่าลืมเข้าร่วมนะครับ ลิงก์: https://example.com')] },
  { cat: 'อีเวนต์', name: 'ตั๋ว / QR เข้างาน', desc: 'Flex ตั๋วมี QR',
    build: () => [flex('ตั๋วเข้างาน', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('🎟️ ตั๋วเข้างาน', { weight: 'bold', size: 'lg', align: 'center' }),
        { type: 'image', url: IMG(300, 300, 'QR'), size: 'md', aspectMode: 'fit' },
        sep(),
        kv('ชื่อ', 'ผู้เข้าร่วม'), kv('รหัส', 'TK-2569-0001'), kv('ที่นั่ง', 'A12'),
      ] },
    }))] },

  // ========== ยืนยัน / แจ้งสถานะ ==========
  { cat: 'ยืนยัน/สถานะ', name: 'ยืนยันคำสั่งซื้อ (ใบเสร็จ)', desc: 'Flex ใบเสร็จ',
    build: () => [flex('ใบเสร็จ', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('✅ ยืนยันการสั่งซื้อ', { weight: 'bold', size: 'lg', color: GREEN }),
        txt('เลขที่ #INV-2569-0042', { size: 'xs', color: '#aaaaaa' }),
        sep(),
        ...[['คอร์สติวเข้ม', '฿1,990'], ['หนังสือ', '฿350']].map(([n, p]) =>
          ({ type: 'box', layout: 'horizontal', contents: [
            { type: 'text', text: n, size: 'sm', color: '#555555' },
            { type: 'text', text: p, size: 'sm', align: 'end', color: '#111111' },
          ] })),
        sep(),
        { type: 'box', layout: 'horizontal', contents: [
          { type: 'text', text: 'รวม', size: 'sm', weight: 'bold' },
          { type: 'text', text: '฿2,340', size: 'sm', weight: 'bold', align: 'end', color: GREEN },
        ] },
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [linkbtn('ดูรายละเอียดคำสั่งซื้อ')] },
    }))] },
  { cat: 'ยืนยัน/สถานะ', name: 'ยืนยัน/ปฏิเสธ (Confirm)', desc: 'Template confirm',
    build: () => [{ type: 'template', altText: 'ยืนยันการนัดหมาย', template: { type: 'confirm',
      text: 'ยืนยันการนัดหมายวันที่ 10 ต.ค. เวลา 14:00 น. หรือไม่?',
      actions: [
        { type: 'message', label: 'ยืนยัน', text: 'ยืนยันนัดหมาย' },
        { type: 'message', label: 'ขอเลื่อน', text: 'ขอเลื่อนนัด' },
      ] } }] },
  { cat: 'ยืนยัน/สถานะ', name: 'แจ้งสถานะการจัดส่ง', desc: 'Flex progress',
    build: () => [flex('สถานะจัดส่ง', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('📦 สถานะพัสดุ', { weight: 'bold', size: 'md' }),
        txt('TH123456789TH', { size: 'xs', color: '#aaaaaa' }),
        { type: 'box', layout: 'horizontal', margin: 'lg', contents:
          ['รับorder', 'แพ็ก', 'จัดส่ง', 'ถึงแล้ว'].map((s, i) => ({
            type: 'box', layout: 'vertical', contents: [
              { type: 'text', text: i <= 2 ? '●' : '○', align: 'center', color: i <= 2 ? GREEN : '#cccccc' },
              { type: 'text', text: s, align: 'center', size: 'xxs', color: '#888888', wrap: true },
            ] })) },
      ] },
    }))] },
  { cat: 'ยืนยัน/สถานะ', name: 'ชำระเงินสำเร็จ', desc: 'ข้อความ + สติกเกอร์',
    build: () => [
      txt('💚 ได้รับการชำระเงินเรียบร้อยแล้ว\nยอด ฿1,990 · เวลา 14:32 น.\nขอบคุณที่ใช้บริการครับ'),
      { type: 'sticker', packageId: '11537', stickerId: '52002735' },
    ] },

  // ========== แบบสอบถาม / โพล ==========
  { cat: 'แบบสอบถาม', name: 'โพลถามความเห็น (ปุ่ม)', desc: 'Template buttons',
    build: () => [{ type: 'template', altText: 'โหวต', template: { type: 'buttons',
      title: 'ช่วยโหวตหน่อยครับ', text: 'คุณอยากให้เปิดคอร์สวิชาไหนเพิ่ม?',
      actions: [
        { type: 'message', label: 'คณิตศาสตร์', text: 'โหวต: คณิต' },
        { type: 'message', label: 'ภาษาอังกฤษ', text: 'โหวต: อังกฤษ' },
        { type: 'message', label: 'วิทยาศาสตร์', text: 'โหวต: วิทย์' },
      ] } }] },
  { cat: 'แบบสอบถาม', name: 'ให้คะแนน 1-5', desc: 'Quick reply ดาว',
    build: () => [{ type: 'text', text: 'ให้คะแนนความพึงพอใจของคุณ ⭐', quickReply: { items:
      [1, 2, 3, 4, 5].map((n) => ({ type: 'action', action: { type: 'message', label: '⭐'.repeat(n), text: `คะแนน ${n}` } })) } }] },
  { cat: 'แบบสอบถาม', name: 'ลิงก์ Google Form', desc: 'Flex เชิญทำแบบสอบถาม',
    build: () => [flex('แบบสอบถาม', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('📝 ขอความร่วมมือทำแบบสอบถาม', { weight: 'bold', size: 'md' }),
        txt('ใช้เวลาไม่เกิน 2 นาที ความเห็นของคุณมีค่ามากครับ', { size: 'sm', color: '#666666' }),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('ทำแบบสอบถาม')] },
    }))] },

  // ========== ติดต่อ / ข้อมูล ==========
  { cat: 'ติดต่อ/ข้อมูล', name: 'นามบัตร / ข้อมูลติดต่อ', desc: 'Flex contact card',
    build: () => [flex('ข้อมูลติดต่อ', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        { type: 'box', layout: 'horizontal', spacing: 'md', contents: [
          { type: 'image', url: IMG(200, 200, 'LOGO'), size: 'sm', flex: 0 },
          { type: 'box', layout: 'vertical', contents: [
            txt('ชื่อสถาบัน', { weight: 'bold', size: 'md' }),
            txt('ติวเตอร์มืออาชีพ', { size: 'xs', color: '#aaaaaa' }),
          ] },
        ] },
        sep(),
        kv('📞 โทร', '02-123-4567'), kv('✉️ อีเมล', 'hello@example.com'),
        kv('🕐 เวลาทำการ', 'จ-ส 09:00-18:00'),
      ] },
      footer: { type: 'box', layout: 'horizontal', spacing: 'sm', contents: [
        { type: 'button', style: 'link', action: { type: 'uri', label: 'โทร', uri: 'tel:021234567' } },
        { type: 'button', style: 'link', action: { type: 'uri', label: 'เว็บไซต์', uri: 'https://example.com' } },
      ] },
    }))] },
  { cat: 'ติดต่อ/ข้อมูล', name: 'แผนที่ / ที่ตั้ง', desc: 'Location message',
    build: () => [{ type: 'location', title: 'สถาบันของเรา', address: '123 ถ.สุขุมวิท กรุงเทพฯ 10110', latitude: 13.7398, longitude: 100.5602 }] },
  { cat: 'ติดต่อ/ข้อมูล', name: 'FAQ คำถามที่พบบ่อย', desc: 'Flex accordion-like',
    build: () => [flex('FAQ', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'lg', contents: [
        txt('❓ คำถามที่พบบ่อย', { weight: 'bold', size: 'lg' }),
        ...[
          ['สมัครยังไง?', 'กดปุ่ม "สมัครเรียน" แล้วกรอกฟอร์ม'],
          ['เรียนออนไลน์ได้ไหม?', 'ได้ครับ มีทั้งสดและย้อนหลัง'],
          ['จ่ายเงินยังไง?', 'โอนผ่านธนาคาร หรือ พร้อมเพย์'],
        ].map(([q, a]) => ({ type: 'box', layout: 'vertical', spacing: 'xs', contents: [
          txt(`Q: ${q}`, { size: 'sm', weight: 'bold', color: GREEN }),
          txt(`A: ${a}`, { size: 'sm', color: '#666666' }),
        ] })),
      ] },
    }))] },
  { cat: 'ติดต่อ/ข้อมูล', name: 'ลิงก์โซเชียลทั้งหมด', desc: 'Buttons รวมช่องทาง',
    build: () => [{ type: 'template', altText: 'ช่องทางติดตาม', template: { type: 'buttons',
      thumbnailImageUrl: IMG(1024, 1024, 'SOCIAL'), title: 'ติดตามเราได้ที่', text: 'เลือกช่องทางที่สะดวก',
      actions: [
        { type: 'uri', label: 'Facebook', uri: 'https://facebook.com' },
        { type: 'uri', label: 'Instagram', uri: 'https://instagram.com' },
        { type: 'uri', label: 'YouTube', uri: 'https://youtube.com' },
        { type: 'uri', label: 'TikTok', uri: 'https://tiktok.com' },
      ] } }] },

  // ========== ขอบคุณ / ติดตามผล ==========
  { cat: 'ขอบคุณ/ติดตาม', name: 'ขอบคุณหลังซื้อ', desc: 'ข้อความอบอุ่น',
    build: () => [txt('ขอบคุณมากครับ 🙏\nทีมงานจะติดต่อกลับภายใน 24 ชม.\nหากมีข้อสงสัยพิมพ์เข้ามาได้เลยครับ')] },
  { cat: 'ขอบคุณ/ติดตาม', name: 'รีวิว / testimonial', desc: 'Flex คำรีวิว',
    build: () => [flex('รีวิว', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        { type: 'text', text: '★★★★★', color: '#f5a623' },
        txt('"เรียนแล้วเข้าใจง่ายมาก คะแนนขึ้นจริง แนะนำเลยครับ"', { size: 'sm', wrap: true, style: 'italic', color: '#555555' }),
        { type: 'box', layout: 'horizontal', spacing: 'sm', contents: [
          { type: 'image', url: IMG(80, 80), size: 'xxs', flex: 0 },
          { type: 'text', text: 'น้องเอ · ม.6', size: 'xs', color: '#aaaaaa', gravity: 'center' },
        ] },
      ] },
    }))] },
  { cat: 'ขอบคุณ/ติดตาม', name: 'บัตรสะสมแต้ม', desc: 'Flex loyalty card',
    build: () => [flex('บัตรสะสมแต้ม', bubble({ size: 'kilo',
      body: { type: 'box', layout: 'vertical', backgroundColor: '#0f172a', paddingAll: 'lg', spacing: 'md', contents: [
        { type: 'box', layout: 'horizontal', contents: [
          { type: 'text', text: 'MEMBER', color: '#ffffff', size: 'xs', weight: 'bold' },
          { type: 'text', text: 'Gold', color: '#f5a623', size: 'xs', align: 'end', weight: 'bold' },
        ] },
        txt('1,250 แต้ม', { color: '#ffffff', size: 'xxl', weight: 'bold' }),
        txt('อีก 250 แต้ม รับส่วนลด ฿100', { color: '#ffffffaa', size: 'xs' }),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [linkbtn('ดูสิทธิประโยชน์')] },
    }))] },
  { cat: 'ขอบคุณ/ติดตาม', name: 'ชวนบอกต่อเพื่อน', desc: 'Referral',
    build: () => [flex('ชวนเพื่อน', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('🎁 ชวนเพื่อน รับส่วนลดทั้งคู่', { weight: 'bold', size: 'md' }),
        txt('ส่งโค้ดนี้ให้เพื่อน เมื่อเพื่อนสมัคร คุณได้ ฿100 เพื่อนได้ ฿100', { size: 'sm', color: '#666666' }),
        { type: 'box', layout: 'vertical', backgroundColor: '#f4f4f4', paddingAll: 'md', cornerRadius: 'md', margin: 'md', contents: [
          { type: 'text', text: 'FRIEND-AB12CD', align: 'center', weight: 'bold', size: 'lg', color: GREEN },
        ] },
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('แชร์ให้เพื่อน')] },
    }))] },

  // ========== การศึกษา (เฉพาะทาง) ==========
  { cat: 'การศึกษา', name: 'แจ้งผลสอบรายบุคคล', desc: 'Flex ผลคะแนน',
    build: () => [flex('ผลสอบ', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
        txt('📊 ผลสอบ Pre-test', { weight: 'bold', size: 'lg' }),
        { type: 'box', layout: 'vertical', backgroundColor: '#ecfdf3', paddingAll: 'lg', cornerRadius: 'md', contents: [
          { type: 'text', text: '78 / 100', align: 'center', size: 'xxl', weight: 'bold', color: GREEN },
          { type: 'text', text: 'อยู่ในเกณฑ์ดี', align: 'center', size: 'xs', color: '#666666' },
        ] },
        kv('อันดับ', '12 จาก 240'), kv('จุดที่ควรพัฒนา', 'พีชคณิต, เรขาคณิต'),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('ดูเฉลยละเอียด')] },
    }))] },
  { cat: 'การศึกษา', name: 'เปิดรับสมัครคอร์ส', desc: 'Flex สมัครเรียน',
    build: () => [flex('เปิดรับสมัคร', bubble({
      hero: { type: 'image', url: IMG(1024, 512, 'COURSE'), size: 'full', aspectRatio: '20:10', aspectMode: 'cover' },
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('🎓 เปิดรับสมัคร คอร์สติวเข้ม', { weight: 'bold', size: 'lg' }),
        kv('เริ่มเรียน', '1 พ.ย. 2569'), kv('จำนวน', 'รับ 30 คน (เหลือ 8 ที่)'),
        kv('ราคา', '฿1,990 (Early bird ฿1,490)'),
      ] },
      footer: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [btn('สมัครเลย'), linkbtn('ดูตารางเรียน')] },
    }))] },
  { cat: 'การศึกษา', name: 'ส่งการบ้าน/เตือนงาน', desc: 'ข้อความเตือน',
    build: () => [{ type: 'text', text: '📚 เตือนส่งการบ้าน: แบบฝึกหัดบทที่ 3 กำหนดส่งพรุ่งนี้ 23:59 น.\nอัปโหลดได้ที่ลิงก์ในคลาสนะครับ', quickReply: { items: [
      { type: 'action', action: { type: 'message', label: 'ส่งแล้ว', text: 'ส่งการบ้านแล้ว' } },
      { type: 'action', action: { type: 'message', label: 'ขอเลื่อน', text: 'ขอเลื่อนส่งการบ้าน' } },
    ] } }] },
  { cat: 'การศึกษา', name: 'ลิงก์ห้องเรียน Zoom', desc: 'Flex เข้าเรียน',
    build: () => [flex('ห้องเรียนวันนี้', bubble({
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        txt('🔴 คลาสสดวันนี้', { weight: 'bold', size: 'md', color: '#dc2626' }),
        kv('วิชา', 'คณิตศาสตร์ - ตรีโกณมิติ'), kv('เวลา', '18:00 - 20:00 น.'),
        kv('รหัสห้อง', '123 456 7890'),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [btn('เข้าห้องเรียน')] },
    }))] },

  // ========== ทั่วไป / ยูทิลิตี้ ==========
  { cat: 'ทั่วไป', name: 'ข้อความ + รูปภาพ', desc: 'text + image',
    build: () => [txt('ดูรายละเอียดเพิ่มเติมได้จากภาพด้านล่างครับ'),
      { type: 'image', originalContentUrl: IMG(1024, 1024, 'IMAGE'), previewImageUrl: IMG(400, 400, 'IMAGE') }] },
  { cat: 'ทั่วไป', name: 'วิดีโอแนะนำ', desc: 'video message',
    build: () => [{ type: 'video', originalContentUrl: 'https://example.com/video.mp4', previewImageUrl: IMG(1024, 576, 'VIDEO') }] },
  { cat: 'ทั่วไป', name: 'ปุ่มลิงก์ 3 อัน', desc: 'Template buttons',
    build: () => [{ type: 'template', altText: 'เมนู', template: { type: 'buttons',
      title: 'เมนูบริการ', text: 'เลือกสิ่งที่ต้องการ',
      actions: [
        { type: 'uri', label: 'สมัครเรียน', uri: 'https://example.com/register' },
        { type: 'uri', label: 'ดูตารางเรียน', uri: 'https://example.com/schedule' },
        { type: 'message', label: 'คุยกับแอดมิน', text: 'ติดต่อแอดมิน' },
      ] } }] },
  { cat: 'ทั่วไป', name: 'ตอบรับอัตโนมัติ (นอกเวลา)', desc: 'ข้อความแจ้งนอกเวลาทำการ',
    build: () => [txt('ขณะนี้อยู่นอกเวลาทำการ (จ-ส 09:00-18:00 น.)\nแอดมินจะตอบกลับในวันทำการถัดไปครับ 🙏\nเรื่องด่วนโทร 02-123-4567')] },
  { cat: 'ทั่วไป', name: 'ขออภัยในความไม่สะดวก', desc: 'ข้อความ',
    build: () => [txt('ขออภัยในความไม่สะดวกครับ 🙇\nระบบขัดข้องชั่วคราว ทีมงานกำลังแก้ไข คาดว่าจะกลับมาใช้งานได้ภายใน 1 ชม.')] },
]

export const CATEGORIES = [...new Set(GALLERY.map((g) => g.cat))]
