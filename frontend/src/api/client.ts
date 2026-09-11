export class ApiError extends Error {
  status: number

  constructor(detail: string, status: number) {
    super(detail)
    this.status = status
  }
}

async function request<T = unknown>(url: string, method = 'GET', body?: unknown): Promise<T> {
  const resp = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const data = await resp.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* 保留 statusText */
    }
    throw new ApiError(detail, resp.status)
  }
  return resp.json()
}

export const api = {
  version: () => request<{ version_name: string; local_version: number; repo: string }>('/api/system/version'),
  checkUpdate: () => request<{ local_version: number; latest: number | null; has_new: boolean }>('/api/system/check-update'),
  info: () => request<Record<string, any>>('/api/system/info'),
  config: () => request<{ config: Record<string, any>; path: string }>('/api/config'),
  putConfig: (config: unknown) => request<{ ok: boolean; errors: string[] }>('/api/config', 'PUT', { config }),
  configFiles: () => request<{ files: string[]; current: string }>('/api/config/files'),
  switchConfig: (name: string) => request<{ ok: boolean; errors: string[] }>('/api/config/switch', 'POST', { name }),
  resetConfig: () => request<{ ok: boolean; errors: string[] }>('/api/config/reset', 'POST'),
  scrapeStatus: () => request<ScrapeStatus>('/api/scrape/status'),
  scrapeResults: (status?: string) =>
    request<{ items: ResultItem[] }>(`/api/scrape/results${status ? `?status=${status}` : ''}`),
  clearResults: () => request('/api/scrape/results', 'DELETE'),
  scrapeStart: (mode = 'default', movieList?: string[]) =>
    request('/api/scrape/start', 'POST', { mode, movie_list: movieList }),
  scrapeResume: () => request('/api/scrape/start', 'POST', { resume: true }),
  scrapeStop: () => request('/api/scrape/stop', 'POST'),
  resumeInfo: () => request<ResumeInfo>('/api/scrape/resume-info'),
  detailLog: () => request<{ text: string }>('/api/scrape/detail-log'),
  retryFailed: () => request<{ ok: boolean; count?: number }>('/api/scrape/retry-failed', 'POST'),
  networkCheck: (retryFailedOnly = false) =>
    request('/api/network/check', 'POST', { retry_failed_only: retryFailedOnly }),
  networkStop: () => request('/api/network/stop', 'POST'),
  networkResults: () => request<{ running: boolean; results: NetworkResult[] }>('/api/network/results'),
}

export interface ScrapeStatus {
  state: string
  progress: number
  results: number
  counts: { succ: number; fail: number; done: number; total: number }
  elapsed: number
}

export interface ResultItem {
  status: string
  real_number: string
  show: ShowData
}

export interface ResumeInfo {
  available: boolean
  count?: number
  first_path?: string
  first_in_scan_dirs?: boolean
  scan_dirs?: string[]
}

export interface NetworkResult {
  spec: { group: string; name: string; url: string }
  status: string
  message: string
  status_code: number | null
  elapsed_ms: number | null
  error: string
}

interface ShowData {
  file_info: Record<string, unknown>
  data: Record<string, unknown>
  other: { poster_path?: string | null; thumb_path?: string | null }
  show_name: string
}

export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null
  return `/api/media/file?path=${encodeURIComponent(path)}`
}

export function videoUrl(path: string | null | undefined): string | null {
  if (!path) return null
  return `/api/media/video?path=${encodeURIComponent(path)}`
}
