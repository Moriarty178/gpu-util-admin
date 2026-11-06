import { describe, expect, it } from 'vitest'
import type { CatalogItem } from '../api/types'
import { editBody, fileValue, type InventoryForm, manualBody } from './inventoryEdit'

// .3 trong file: dịch vụ 'Embedding', model 'model-x'; admin đã sửa dịch vụ → 'Rerank'
const row = {
  inventory_ip: '192.0.2.3',
  owner: 'kientt6',
  model: 'model-x',
  input_load: '10',
  service: 'Rerank',
  managed_by: 'Server độc lập',
  cluster: null,
  reclaim_status: 'in_use',
  edited: { service: 'Embedding' },
} as unknown as CatalogItem

const form = (over: Partial<InventoryForm> = {}): InventoryForm => ({
  owner: 'kientt6',
  model: 'model-x',
  input_load: '10',
  service: 'Rerank',
  managed_by: 'Server độc lập',
  cluster: '',
  reclaim_status: 'in_use',
  ...over,
})

describe('fileValue', () => {
  it('ô đã sửa tay → giá trị theo file; ô khác → giá trị đang hiện', () => {
    expect(fileValue(row, 'service')).toBe('Embedding')
    expect(fileValue(row, 'model')).toBe('model-x')
    expect(fileValue(row, 'cluster')).toBeNull()
  })
})

describe('editBody', () => {
  it('không đổi gì → thân rỗng', () => {
    expect(editBody(row, form())).toEqual({})
  })
  it('chỉ gửi ô thay đổi; khoảng trắng bị cắt', () => {
    expect(editBody(row, form({ model: '  model-y ', reclaim_status: 'reclaimed' }))).toEqual({
      model: 'model-y',
      reclaim_status: 'reclaimed',
    })
  })
  it('đặt lại đúng giá trị file → null (về theo file)', () => {
    expect(editBody(row, form({ service: 'Embedding' }))).toEqual({ service: null })
  })
  it("xóa trắng ô có giá trị → '' (để trống)", () => {
    expect(editBody(row, form({ model: '' }))).toEqual({ model: '' })
  })
})

describe('manualBody', () => {
  it('cắt khoảng trắng, bỏ ô trống, mặc định Đang sử dụng', () => {
    expect(manualBody('192.0.2.6', { owner: ' kientt6 ', gpu_spec: '8*H200', cpu: '  ', service: 'Train ' })).toEqual({
      ip: '192.0.2.6',
      owner: 'kientt6',
      reclaim_status: 'in_use',
      gpu_spec: '8*H200',
      service: 'Train',
    })
  })
})
