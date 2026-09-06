// เทมเพลต Flex เริ่มต้น — เลือกแล้วแก้ต่อ

export const FLEX_TEMPLATES = {
  product: {
    label: 'การ์ดสินค้า/คอร์ส',
    build: () => ({
      type: 'flex',
      altText: 'การ์ดสินค้า',
      contents: {
        type: 'bubble',
        hero: { type: 'image', url: 'https://via.placeholder.com/1024x512', size: 'full', aspectRatio: '20:13', aspectMode: 'cover' },
        body: {
          type: 'box', layout: 'vertical', spacing: 'sm',
          contents: [
            { type: 'text', text: 'ชื่อคอร์ส', weight: 'bold', size: 'xl' },
            { type: 'box', layout: 'baseline', contents: [
              { type: 'text', text: '฿1,990', weight: 'bold', size: 'lg', flex: 0 },
              { type: 'text', text: '฿2,990', size: 'sm', color: '#aaaaaa', decoration: 'line-through', margin: 'sm' },
            ] },
            { type: 'text', text: 'รายละเอียดสั้น ๆ เกี่ยวกับคอร์สนี้', size: 'sm', color: '#666666', wrap: true },
          ],
        },
        footer: {
          type: 'box', layout: 'vertical', spacing: 'sm',
          contents: [
            { type: 'button', style: 'primary', color: '#06c755', action: { type: 'uri', label: 'สมัครเลย', uri: 'https://example.com' } },
            { type: 'button', style: 'link', action: { type: 'uri', label: 'ดูรายละเอียด', uri: 'https://example.com' } },
          ],
        },
      },
    }),
  },
  notice: {
    label: 'ประกาศ/แจ้งเตือน',
    build: () => ({
      type: 'flex', altText: 'ประกาศ',
      contents: {
        type: 'bubble',
        body: {
          type: 'box', layout: 'vertical', spacing: 'md',
          contents: [
            { type: 'text', text: '📢 ประกาศ', weight: 'bold', size: 'lg', color: '#06c755' },
            { type: 'separator' },
            { type: 'text', text: 'เนื้อหาประกาศ อธิบายรายละเอียดได้หลายบรรทัด', wrap: true, size: 'sm' },
            { type: 'box', layout: 'vertical', margin: 'md', contents: [
              { type: 'box', layout: 'baseline', spacing: 'sm', contents: [
                { type: 'text', text: 'วันที่', color: '#aaaaaa', size: 'sm', flex: 1 },
                { type: 'text', text: '1 ต.ค. 2569', wrap: true, color: '#666666', size: 'sm', flex: 3 },
              ] },
            ] },
          ],
        },
        footer: { type: 'box', layout: 'vertical', contents: [
          { type: 'button', style: 'primary', color: '#06c755', action: { type: 'uri', label: 'อ่านเพิ่ม', uri: 'https://example.com' } },
        ] },
      },
    }),
  },
  coupon: {
    label: 'คูปอง/โปรโมชัน',
    build: () => ({
      type: 'flex', altText: 'คูปองส่วนลด',
      contents: {
        type: 'bubble', size: 'kilo',
        body: {
          type: 'box', layout: 'vertical', backgroundColor: '#06c755', paddingAll: 'lg',
          contents: [
            { type: 'text', text: 'ส่วนลดพิเศษ', color: '#ffffff', size: 'sm' },
            { type: 'text', text: '50%', color: '#ffffff', size: '4xl', weight: 'bold' },
            { type: 'text', text: 'ใช้โค้ด SAVE50 · หมดเขต 31 ต.ค.', color: '#ffffffcc', size: 'xs', margin: 'md' },
            { type: 'button', style: 'secondary', margin: 'lg', action: { type: 'uri', label: 'ใช้เลย', uri: 'https://example.com' } },
          ],
        },
      },
    }),
  },
  minimal: {
    label: 'ข้อความ + ปุ่มเดียว',
    build: () => ({
      type: 'flex', altText: 'ข้อความ',
      contents: {
        type: 'bubble',
        body: { type: 'box', layout: 'vertical', spacing: 'md', contents: [
          { type: 'text', text: 'หัวข้อ', weight: 'bold', size: 'lg' },
          { type: 'text', text: 'เนื้อหา', wrap: true, size: 'sm', color: '#666666' },
          { type: 'button', style: 'primary', color: '#06c755', margin: 'md', action: { type: 'uri', label: 'กดที่นี่', uri: 'https://example.com' } },
        ] },
      },
    }),
  },
  carousel3: {
    label: 'การ์ดสไลด์ 3 ใบ',
    build: () => ({
      type: 'flex', altText: 'การ์ดสไลด์',
      contents: {
        type: 'carousel',
        contents: [1, 2, 3].map((n) => ({
          type: 'bubble', size: 'micro',
          hero: { type: 'image', url: 'https://via.placeholder.com/300x200', size: 'full', aspectRatio: '3:2', aspectMode: 'cover' },
          body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
            { type: 'text', text: `รายการ ${n}`, weight: 'bold', size: 'sm' },
            { type: 'text', text: 'คำอธิบาย', size: 'xs', color: '#888888', wrap: true },
          ] },
          footer: { type: 'box', layout: 'vertical', contents: [
            { type: 'button', style: 'link', height: 'sm', action: { type: 'uri', label: 'ดู', uri: 'https://example.com' } },
          ] },
        })),
      },
    }),
  },
}
