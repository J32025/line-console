// เทมเพลตเปล่าของ LINE message แต่ละชนิด

export const STICKERS = [
  { packageId: '446', stickerId: '1988', label: 'บราวน์ยิ้ม' },
  { packageId: '446', stickerId: '1989', label: 'บราวน์ตกใจ' },
  { packageId: '446', stickerId: '2007', label: 'โคนี่หัวใจ' },
  { packageId: '789', stickerId: '10855', label: 'ยกนิ้ว' },
  { packageId: '789', stickerId: '10877', label: 'ขอบคุณ' },
  { packageId: '11537', stickerId: '52002734', label: 'OK' },
  { packageId: '11538', stickerId: '51626494', label: 'สวัสดี' },
]

export function blank(type) {
  switch (type) {
    case 'text':
      return { type: 'text', text: '' }
    case 'sticker':
      return { type: 'sticker', packageId: '446', stickerId: '1988' }
    case 'image':
      return { type: 'image', originalContentUrl: '', previewImageUrl: '' }
    case 'video':
      return { type: 'video', originalContentUrl: '', previewImageUrl: '' }
    case 'audio':
      return { type: 'audio', originalContentUrl: '', duration: 60000 }
    case 'location':
      return { type: 'location', title: '', address: '', latitude: 13.7563, longitude: 100.5018 }
    case 'buttons':
      return {
        type: 'template',
        altText: 'ปุ่มเมนู',
        template: {
          type: 'buttons',
          thumbnailImageUrl: '',
          title: 'หัวข้อ',
          text: 'รายละเอียด',
          actions: [{ type: 'uri', label: 'เปิดลิงก์', uri: 'https://example.com' }],
        },
      }
    case 'confirm':
      return {
        type: 'template',
        altText: 'ยืนยัน',
        template: {
          type: 'confirm',
          text: 'ยืนยันหรือไม่?',
          actions: [
            { type: 'message', label: 'ใช่', text: 'ใช่' },
            { type: 'message', label: 'ไม่', text: 'ไม่' },
          ],
        },
      }
    case 'carousel':
      return {
        type: 'template',
        altText: 'การ์ดสไลด์',
        template: {
          type: 'carousel',
          columns: [
            {
              thumbnailImageUrl: '',
              title: 'การ์ด 1',
              text: 'รายละเอียด',
              actions: [{ type: 'uri', label: 'ดู', uri: 'https://example.com' }],
            },
          ],
        },
      }
    case 'flex':
      return {
        type: 'flex',
        altText: 'ข้อความ Flex',
        contents: {
          type: 'bubble',
          hero: {
            type: 'image', url: 'https://via.placeholder.com/1024x512',
            size: 'full', aspectRatio: '20:10', aspectMode: 'cover',
          },
          body: {
            type: 'box', layout: 'vertical',
            contents: [
              { type: 'text', text: 'หัวข้อ', weight: 'bold', size: 'xl' },
              { type: 'text', text: 'รายละเอียด', size: 'sm', color: '#888888', wrap: true },
            ],
          },
          footer: {
            type: 'box', layout: 'vertical',
            contents: [
              {
                type: 'button', style: 'primary', color: '#06c755',
                action: { type: 'uri', label: 'เปิด', uri: 'https://example.com' },
              },
            ],
          },
        },
      }
    case 'raw':
      return { type: 'text', text: 'แก้ JSON ด้านล่าง' }
    default:
      return { type: 'text', text: '' }
  }
}

export const TYPE_LABELS = {
  text: 'ข้อความ', sticker: 'สติกเกอร์', image: 'รูปภาพ', video: 'วิดีโอ',
  audio: 'เสียง', location: 'ตำแหน่ง', buttons: 'ปุ่ม (Buttons)', confirm: 'ยืนยัน (Confirm)',
  carousel: 'การ์ดสไลด์ (Carousel)', flex: 'Flex', raw: 'JSON ดิบ',
}

export function detectKind(msg) {
  if (!msg || typeof msg !== 'object') return 'raw'
  if (msg.type === 'template') return msg.template?.type || 'raw'
  return msg.type
}
