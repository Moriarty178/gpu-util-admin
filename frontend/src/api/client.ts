import { vi } from '../lib/vi'

/** Lỗi API chuẩn của backend: {type, title, detail} (tiếng Việt). */
export interface Problem {
  type: string
  title: string
  detail?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly problem: Problem

  constructor(status: number, problem: Problem) {
    super(problem.title)
    this.status = status
    this.problem = problem
  }

  /** Câu thông báo cho người dùng: ưu tiên `detail` (đã là tiếng Việt). */
  get userMessage(): string {
    const d = this.problem.detail
    if (typeof d === 'string' && d) return d
    if (Array.isArray(d)) return d.map((x) => (typeof x === 'object' && x && 'msg' in x ? String(x.msg) : String(x))).join('; ')
    return this.problem.title
  }
}

export const API_BASE = '/api/v1'

// Phiên đăng nhập (G2-M2): cookie httpOnly do backend đặt; cookie gpu_csrf đọc được → gửi lại qua header cho request ghi.
export const CSRF_COOKIE = 'gpu_csrf'
export const CSRF_HEADER = 'X-CSRF-Token'
/** Sự kiện window khi API báo cần đăng nhập lại / phải đổi mật khẩu → AuthGate tải lại /auth/me. */
export const AUTH_EVENT = 'gpu-auth-changed'
const AUTH_TYPES = new Set(['not_authenticated', 'setup_required', 'password_change_required'])

/** Đọc 1 cookie theo tên từ chuỗi document.cookie (hàm thuần, có test). */
export function readCookie(cookies: string, name: string): string | null {
  for (const part of cookies.split(';')) {
    const i = part.indexOf('=')
    if (i > 0 && part.slice(0, i).trim() === name) return decodeURIComponent(part.slice(i + 1).trim())
  }
  return null
}

function writeHeaders(json = false): HeadersInit {
  const h: Record<string, string> = { Accept: 'application/json' }
  const csrf = readCookie(document.cookie, CSRF_COOKIE)
  if (csrf) h[CSRF_HEADER] = csrf
  if (json) h['Content-Type'] = 'application/json'
  return h
}

export function apiUrl(path: string, params?: URLSearchParams): string {
  const qs = params?.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

/** Có phát sự kiện 'cần đăng nhập lại' không: không cho chính /auth/* (tránh vòng lặp /auth/me → 401 → tải lại /auth/me). */
export function signalsAuthChange(path: string, problemType: string): boolean {
  return AUTH_TYPES.has(problemType) && !path.startsWith('/auth/')
}

async function parse<T>(res: Response, path: string): Promise<T> {
  if (!res.ok) {
    let problem: Problem
    try {
      problem = (await res.json()) as Problem
    } catch {
      problem = { type: 'http_error', title: vi.api.httpError(res.status) }
    }
    if (signalsAuthChange(path, problem.type)) window.dispatchEvent(new Event(AUTH_EVENT))
    throw new ApiError(res.status, problem)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export async function apiGet<T>(path: string, params?: URLSearchParams, signal?: AbortSignal): Promise<T> {
  return parse<T>(await fetch(apiUrl(path, params), { signal, headers: { Accept: 'application/json' } }), path)
}

export async function apiPost<T>(path: string, json?: unknown): Promise<T> {
  return apiSend<T>('POST', path, json)
}

export async function apiSend<T>(method: 'POST' | 'PATCH' | 'PUT' | 'DELETE', path: string, json?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: writeHeaders(json !== undefined) }
  if (json !== undefined) init.body = JSON.stringify(json)
  return parse<T>(await fetch(apiUrl(path), init), path)
}

/** Tên file từ Content-Disposition: filename* (UTF-8) → filename → `fallback`. */
export function fileNameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (star) {
    try {
      return decodeURIComponent((star[1] ?? '').trim()) || fallback
    } catch {
      /* rơi về filename thường */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain?.[1] ?? fallback
}

/** POST JSON, nhận file (vd .pptx) — lỗi trả về Problem như các API khác. */
export async function apiDownload(path: string, json: unknown, fallbackName: string): Promise<{ blob: Blob; fileName: string }> {
  const res = await fetch(apiUrl(path), { method: 'POST', headers: writeHeaders(true), body: JSON.stringify(json) })
  if (!res.ok) await parse<never>(res, path)
  return { blob: await res.blob(), fileName: fileNameFromDisposition(res.headers.get('Content-Disposition'), fallbackName) }
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file, file.name)
  return parse<T>(await fetch(apiUrl(path), { method: 'POST', body, headers: writeHeaders() }), path)
}

/** Lỗi 4xx (trừ 408/429) không thử lại — vd hết phiên, không có quyền, 404. */
export function shouldRetry(failureCount: number, err: unknown): boolean {
  if (err instanceof ApiError && err.status >= 400 && err.status < 500 && ![408, 429].includes(err.status)) return false
  return failureCount < 1
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.userMessage
  if (err instanceof Error) return err.message
  return String(err)
}
