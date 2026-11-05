import type { ThemeConfig } from 'antd'

// Phong cách Viettel (người dùng chốt 05/11/2026, ảnh tham khảo VOffice): đỏ Viettel cho thương hiệu, nút, tab, hover;
// sidebar gần đen; nền nội dung xám nhạt. Màu VÙNG vẫn tập trung ở lib/zones.ts — "Nguy hiểm" luôn kèm chữ + biểu tượng
// (ZoneTag) nên không lẫn với đỏ thương hiệu.
export const VIETTEL_RED = '#ee0033'
export const VIETTEL_RED_DARK = '#c8002b' // hover / nhấn trên nền đỏ
export const SIDER_BG = '#241d1e'
export const SIDER_HOVER = '#3a3132'
export const CONTENT_BG = '#e6e6e6'
export const INFO = '#1f2433' // navy phụ của bộ nhận diện — thông báo thông tin (không dùng xanh dương mặc định)
export const HEADER_H = 52
export const SIDER_W = 220

export const theme: ThemeConfig = {
  token: {
    colorPrimary: VIETTEL_RED,
    colorLink: VIETTEL_RED,
    colorInfo: INFO,
    colorInfoBg: '#f3f4f6', // thông báo thông tin: nền xám sáng (seed navy mặc định cho nền quá đậm)
    colorInfoBorder: '#d5d8de',
    borderRadius: 6,
    fontFamily: "Roboto, 'Segoe UI', Arial, sans-serif",
  },
  components: {
    Layout: {
      siderBg: SIDER_BG,
      triggerBg: SIDER_HOVER,
      headerBg: '#ffffff',
      headerHeight: HEADER_H,
      headerPadding: 0,
      bodyBg: CONTENT_BG,
    },
    Menu: {
      darkItemBg: SIDER_BG,
      darkSubMenuItemBg: SIDER_BG,
      darkItemColor: '#ffffff',
      darkItemHoverBg: SIDER_HOVER,
      darkItemHoverColor: '#ffffff',
      darkItemSelectedBg: VIETTEL_RED,
      darkItemSelectedColor: '#ffffff',
      itemBorderRadius: 0,
      itemMarginInline: 0,
      itemMarginBlock: 0,
      itemHeight: 42,
    },
    Tabs: { inkBarColor: VIETTEL_RED, itemSelectedColor: VIETTEL_RED, itemHoverColor: VIETTEL_RED_DARK },
  },
}
