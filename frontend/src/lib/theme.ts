import type { ThemeConfig } from 'antd'

// Primary navy. Đỏ chỉ dành cho vùng "Nguy hiểm" (màu vùng tập trung ở lib/zones.ts — G1-M3).
export const NAVY = '#1f3a68'
export const NAVY_DARK = '#14284b'

export const theme: ThemeConfig = {
  token: { colorPrimary: NAVY, colorLink: NAVY, borderRadius: 6 },
  components: {
    Layout: { siderBg: NAVY_DARK, triggerBg: NAVY, headerBg: '#ffffff' },
    Menu: { darkItemBg: NAVY_DARK, darkSubMenuItemBg: NAVY_DARK, darkItemSelectedBg: NAVY },
  },
}
