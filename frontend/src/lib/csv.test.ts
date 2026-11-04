import { describe, expect, it } from 'vitest'
import { toCsv } from './csv'

describe('toCsv', () => {
  it('BOM, ";" và trích dẫn ô có ký tự đặc biệt', () => {
    const out = toCsv(['IP', 'Dịch vụ'], [['10.0.0.1', 'OCR; KYC'], ['10.0.0.2', 'nói "hi"']])
    expect(out.startsWith('\uFEFF')).toBe(true)
    expect(out.split('\r\n')).toEqual(['\uFEFFIP;Dịch vụ', '10.0.0.1;"OCR; KYC"', '10.0.0.2;"nói ""hi"""'])
  })
  it('chặn chèn công thức Excel (=, +, -, @) ở ô văn bản; giữ nguyên số âm', () => {
    const out = toCsv(['a', 'b', 'c', 'd', 'e', 'f'], [['=HYPERLINK("x")', '+1+1', '@SUM(A1)', '-12,3', -5, '-cmd']])
    expect(out.split('\r\n')[1]).toBe(`"'=HYPERLINK(""x"")";'+1+1;'@SUM(A1);-12,3;-5;'-cmd`)
  })
})
