import { expect, type Page, test } from '@playwright/test'

// Dữ liệu: backend/tests/e2e_server.py (tổng hợp 2 kỳ). Kỳ mới nhất 01–05/11/2026, T=40:
// Nguy hiểm = .2 (dungha7), .6 (VTNet-only), .7 (kientt6). kientt6: .3 An toàn, .4 Cảnh báo, .7 Nguy hiểm.
const ADMIN = { user: 'admin', pass: 'Mat-khau-test-01' } // = TEST_PASSWORD (chỉ dùng cho test, CSDL tạm)
const OWNER_NEW_PASS = 'Dau-moi-e2e-2026'

async function login(page: Page, user: string, pass: string) {
  await page.goto('/')
  await page.getByLabel('Tên đăng nhập').fill(user)
  await page.getByLabel('Mật khẩu', { exact: true }).fill(pass)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
}

async function logout(page: Page) {
  await page.locator('header').getByRole('button').last().click()
  await page.getByText('Đăng xuất').click()
  await expect(page.getByRole('button', { name: 'Đăng nhập' })).toBeVisible()
}

function dangerRows(page: Page) {
  return page.locator('.ant-table-tbody tr.ant-table-row')
}

test.describe.serial('luồng admin → đầu mối', () => {
  let tempPassword = ''

  test('admin: đăng nhập sai báo lỗi, đăng nhập đúng xem cảnh báo', async ({ page }) => {
    await login(page, ADMIN.user, 'sai-mat-khau')
    await expect(page.getByText('Sai tên đăng nhập hoặc mật khẩu.')).toBeVisible()
    await page.getByLabel('Mật khẩu', { exact: true }).fill(ADMIN.pass)
    await page.getByRole('button', { name: 'Đăng nhập' }).click()
    await expect(page.getByRole('menuitem', { name: 'Nhập dữ liệu' })).toBeVisible()
    await page.getByRole('menuitem', { name: 'Cảnh báo' }).click()
    await expect(dangerRows(page)).toHaveCount(3)
    for (const ip of ['192.0.2.2', '192.0.2.6', '192.0.2.7']) await expect(page.getByRole('link', { name: ip })).toBeVisible()
  })

  test('admin: tạo tài khoản đầu mối, mật khẩu tạm hiện 1 lần', async ({ page }) => {
    await login(page, ADMIN.user, ADMIN.pass)
    await page.getByRole('menuitem', { name: 'Tài khoản' }).click()
    await page.getByRole('button', { name: 'Tạo tài khoản' }).click()
    const dlg = page.getByRole('dialog')
    await dlg.getByLabel('Tên đăng nhập').fill('kientt6')
    await dlg.getByLabel('Mã đầu mối').fill('kientt6')
    await dlg.getByRole('button', { name: 'Lưu' }).click()
    const shown = page.getByRole('dialog').filter({ hasText: 'Mật khẩu tạm' })
    await expect(shown).toBeVisible()
    tempPassword = (await shown.locator('.ant-typography').last().innerText()).trim()
    expect(tempPassword).toMatch(/^[A-Za-z0-9]{14}$/)
    await shown.getByRole('button', { name: 'Đóng' }).last().click()
    await expect(page.getByRole('cell', { name: 'kientt6' }).first()).toBeVisible()
    await logout(page)
  })

  test('đầu mối: buộc đổi mật khẩu, chỉ thấy server của mình, không vào được Nhập dữ liệu', async ({ page }) => {
    await login(page, 'kientt6', tempPassword)
    await expect(page.getByText('Đây là mật khẩu tạm')).toBeVisible()
    await page.getByLabel('Mật khẩu hiện tại').fill(tempPassword)
    await page.getByLabel('Mật khẩu mới', { exact: true }).fill(OWNER_NEW_PASS)
    await page.getByLabel('Nhập lại mật khẩu mới').fill(OWNER_NEW_PASS)
    await page.getByRole('button', { name: 'Lưu mật khẩu mới' }).click()
    await expect(page.getByText('Bạn đang xem server của đầu mối kientt6.')).toBeVisible()
    const menu = page.getByRole('menu')
    await expect(menu.getByRole('menuitem')).toHaveText(['Tổng quan', 'Cảnh báo', 'Server', 'Danh mục server', 'So sánh'])
    await menu.getByRole('menuitem', { name: 'Cảnh báo' }).click()
    await expect(dangerRows(page)).toHaveCount(1)
    await expect(page.getByRole('link', { name: '192.0.2.7' })).toBeVisible()
    await page.goto('/imports')
    await expect(page.getByText('Không có quyền')).toBeVisible()
    await page.goto('/servers/192.0.2.1')
    await expect(page.getByText('Không tìm thấy server')).toBeVisible()
  })

  test('đầu mối: thêm giải trình; admin thấy trong Nhật ký', async ({ page }) => {
    await login(page, 'kientt6', OWNER_NEW_PASS)
    await page.goto('/servers/192.0.2.7')
    await page.getByLabel('Nội dung').fill('Đang chạy thử mô hình mới, sẽ tối ưu trong tháng 12')
    await page.getByRole('button', { name: 'Thêm', exact: true }).click()
    await expect(page.getByText('Đang chạy thử mô hình mới, sẽ tối ưu trong tháng 12')).toBeVisible()
    await logout(page)
    await login(page, ADMIN.user, ADMIN.pass)
    await page.getByRole('menuitem', { name: 'Nhật ký' }).click()
    const row = page.locator('.ant-table-tbody tr', { hasText: 'Thêm ghi chú' }).first()
    await expect(row).toContainText('kientt6')
    await expect(page.locator('.ant-table-tbody tr', { hasText: 'Tạo tài khoản' }).first()).toContainText('admin')
  })
})

test('admin: báo cáo tháng — sửa thông điệp rồi tải deck .pptx', async ({ page }) => {
  await login(page, ADMIN.user, ADMIN.pass)
  await page.getByRole('menuitem', { name: 'Báo cáo tháng' }).click()
  // dữ liệu E2E: 01–05/10 + 01–05/11 → tháng 10 đã qua (xuất được), tháng 11 chưa đủ → mặc định = tháng 10 (PLAN §14.8)
  await expect(page.locator('.ant-select-selection-item')).toHaveText('Tháng 10/2026')
  await expect(page.getByText(/2\/\d+ server Nguy hiểm/)).toBeVisible() // thông điệp gợi ý từ số liệu
  await expect(page.getByText(/Tháng đã qua nhưng thiếu 26 ngày/)).toBeVisible() // 06–31/10 không có số liệu
  await page.locator('textarea').first().fill('Thông điệp E2E do admin viết.')
  await expect(page.getByText('Đã sửa so với gợi ý')).toBeVisible()
  const [file] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Tải báo cáo (.pptx)' }).click()])
  expect(file.suggestedFilename()).toBe('Bao_cao_GPU_thang_10_2026.pptx')
  await expect(page.getByText('Đã tải Bao_cao_GPU_thang_10_2026.pptx')).toBeVisible()
  // tháng chưa đủ dữ liệu → cảnh báo + khóa nút tải
  await page.locator('.ant-select-selector').first().click()
  await page.getByTitle('Tháng 11/2026 — chưa đủ dữ liệu').click()
  await expect(page.getByText(/Tháng 11\/2026 chưa đủ dữ liệu: mới có dữ liệu tới 05\/11\/2026 \(5\/30 ngày\)/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Tải báo cáo (.pptx)' })).toBeDisabled()
})

test('admin: tải file có cảnh báo → xem trước + kiểm tra → phải xác nhận đã xem mới nhập', async ({ page }) => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  await login(page, ADMIN.user, ADMIN.pass)
  await page.getByRole('menuitem', { name: 'Nhập dữ liệu' }).click()
  // file tổng hợp tháng 10 nhưng đặt tên "Thang 8" → cảnh báo "Tên file ghi tháng 8…"
  const buffer = fs.readFileSync(path.resolve('../backend/tests/fixtures/synthetic_t7.xlsx')) // Playwright chạy từ frontend/
  await page.locator('input[type=file]').setInputFiles({ name: 'HSSD GPU Thang 8 2026 - VTT.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer })
  await expect(page.getByText('Xem trước tác động (T = 40%)')).toBeVisible()
  await expect(page.getByText('Tên file ghi tháng 8 nhưng dữ liệu chủ yếu là tháng 10')).toBeVisible()
  const card = page.locator('.ant-card', { hasText: 'Xem trước lô' }).first()
  await card.getByRole('button', { name: 'Xác nhận nhập' }).click()
  await expect(page.getByText('Lô có 1 cảnh báo — đã xem và vẫn nhập?')).toBeVisible()
  await page.getByRole('button', { name: 'Đã xem, nhập' }).click()
  await expect(page.getByText(/Đã nhập lô #\d+/)).toBeVisible()
})
