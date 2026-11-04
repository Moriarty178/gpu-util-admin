// CSV cho Excel tiếng Việt trên Windows: BOM UTF-8, phân cách ';', thập phân ','.

export type CsvCell = string | number | null | undefined

// Ô văn bản bắt đầu bằng = + - @ (hoặc tab/CR) bị Excel coi là công thức → thêm dấu ' ở đầu (chặn chèn công thức qua dữ liệu
// file thống kê). Số (kể cả số âm dạng '-12,3') giữ nguyên.
const FORMULA_START = /^[=+\-@\t\r]/
const NUMERIC = /^-?[\d.,]+%?$/

function cell(v: CsvCell): string {
  if (v === null || v === undefined) return ''
  let s = String(v)
  if (typeof v === 'string' && FORMULA_START.test(s) && !NUMERIC.test(s)) s = "'" + s
  return /[";\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(header: string[], rows: CsvCell[][]): string {
  return '﻿' + [header, ...rows].map((r) => r.map(cell).join(';')).join('\r\n')
}

export function downloadText(text: string, fileName: string, mime = 'text/csv;charset=utf-8'): void {
  downloadBlob(new Blob([text], { type: mime }), fileName)
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
