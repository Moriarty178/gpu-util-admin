import viettelLogo from '../assets/viettel-logo.png'
import { HEADER_H, VIETTEL_RED } from '../lib/theme'
import { vi } from '../lib/vi'

/** Biểu tượng chip GPU (trắng) — vẽ tại chỗ, không tải tài nguyên ngoài. */
function ChipIcon({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="6" y="6" width="20" height="20" rx="3" fill="none" stroke="#fff" strokeWidth="2.5" />
      <rect x="11.5" y="11.5" width="9" height="9" rx="1.5" fill="#fff" />
      <g stroke="#fff" strokeWidth="2" strokeLinecap="round">
        <path d="M11 2v3M16 2v3M21 2v3M11 27v3M16 27v3M21 27v3M2 11h3M2 16h3M2 21h3M27 11h3M27 16h3M27 21h3" />
      </g>
    </svg>
  )
}

/** Khối tên "GPU Util" nền đỏ, cạnh phải cắt chéo (theo ảnh tham khảo VOffice) — góc trên bên trái. */
export function BrandBlock({ width }: { width: number }) {
  return (
    <div
      style={{
        width,
        height: HEADER_H,
        flex: 'none',
        background: VIETTEL_RED,
        clipPath: 'polygon(0 0, 100% 0, calc(100% - 26px) 100%, 0 100%)',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 36px 0 18px',
        color: '#fff',
      }}
    >
      <ChipIcon />
      <span style={{ fontSize: 21, fontWeight: 700, letterSpacing: 0.2, whiteSpace: 'nowrap' }}>{vi.brand}</span>
    </div>
  )
}

export function ViettelLogo({ height = 24 }: { height?: number }) {
  return <img src={viettelLogo} alt="Viettel" style={{ height, width: 'auto', display: 'block' }} />
}
