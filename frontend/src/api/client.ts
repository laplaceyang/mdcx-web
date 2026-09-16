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
  // ===== 工具页 =====
  toolsStatus: () => request<{ running: string[] }>('/api/tools/status'),
  configSites: () => request<{ sites: { site: string; url: string }[] }>('/api/config/sites'),
  mediaBrowse: (path = '') =>
    request<{ roots?: string[]; current?: string; parent?: string; dirs: string[]; files: string[] }>(
      `/api/fs/media-browse?path=${encodeURIComponent(path)}`,
    ),
  singleScrape: (filePath: string, appointUrl: string) =>
    request('/api/scrape/start', 'POST', { mode: 'single', file_path: filePath, appoint_url: appointUrl }),
  toolsSymlink: (copyNfo: boolean) => request('/api/tools/symlink', 'POST', { copy_nfo: copyNfo }),
  toolsMoveVideos: () => request('/api/tools/move-videos', 'POST'),
  toolsSubtitle: () => request('/api/tools/subtitle', 'POST'),
  toolsExtras: (kind: string, action: string) => request('/api/tools/extras', 'POST', { kind, action }),
  toolsCoverBackfill: (numbers: string[], overwrite: boolean, watermark: boolean) =>
    request('/api/tools/cover-backfill', 'POST', { numbers, overwrite, watermark }),
  toolsGfriends: (localPath: string) => request('/api/tools/gfriends', 'POST', { local_path: localPath }),
  toolsActorDb: (task: string, params: Record<string, unknown> = {}) =>
    request('/api/tools/actor-db', 'POST', { task, ...params }),
  toolsMissingNumber: () => request('/api/tools/missing-number', 'POST'),
  cacheStats: () => request<{ stats: Record<string, any>; failed: CacheFailedItem[] }>('/api/tools/cache/stats'),
  cacheExport: () => `${apiBase()}/api/tools/cache/export`,
  cacheDelete: (paths: string[]) => request('/api/tools/cache/delete', 'POST', { paths }),
  cacheClear: () => request('/api/tools/cache/clear', 'POST'),
  posterCut: (path: string, box: [number, number, number, number], outputPath = '') =>
    request('/api/tools/poster-cut', 'POST', { path, box, output_path: outputPath }),
  coverBackfillUpload: (number: string, file: File, overwrite: boolean) =>
    fetch(
      `/api/tools/cover-backfill/upload?number=${encodeURIComponent(number)}&filename=${encodeURIComponent(
        file.name,
      )}&overwrite=${overwrite}`,
      { method: 'POST', body: file },
    ).then(async (resp) => {
      if (!resp.ok) {
        let detail = resp.statusText
        try {
          detail = (await resp.json()).detail ?? detail
        } catch {
          /* keep statusText */
        }
        throw new Error(detail)
      }
      return resp.json() as Promise<{ ok: boolean; number: string; thumb: string; poster: string }>
    }),
  translateTest: (mode: 'text' | 'nfo', payload: { text?: string; path?: string; field?: 'title' | 'outline' }) =>
    request<{
      mode: string
      original?: string
      content: string
      path?: string
      log?: string
      field_info?: Record<string, any>
    }>('/api/tools/translate-test', 'POST', {
      mode,
      ...payload,
    }),
  translateTestSave: (path: string, content: string) =>
    request<{ ok: boolean; path: string; bak: string }>('/api/tools/translate-test/save', 'POST', { path, content }),
  actorInfoSync: () => request('/api/tools/actor-info-sync', 'POST'),
  actorPhotoSync: () => request('/api/tools/actor-photo-sync', 'POST'),
  actorKodiWrite: () => request('/api/tools/actor-kodi-write', 'POST'),
  actorKodiDelete: () => request('/api/tools/actor-kodi-delete', 'POST'),
  // ===== NFO 信息管理 =====
  nfoRoots: () => request<{ roots: string[] }>('/api/nfo/roots'),
  nfoBrowse: (path = '', keyword = '') =>
    request<{ dirs: string[]; items: NfoSummary[]; current?: string }>(
      `/api/nfo/browse?path=${encodeURIComponent(path)}&keyword=${encodeURIComponent(keyword)}`,
    ),
  nfoItem: (path: string) =>
    request<{ path: string; fields: Record<string, any>; images: Record<string, string> }>(
      `/api/nfo/item?path=${encodeURIComponent(path)}`,
    ),
  nfoSave: (path: string, fields: Record<string, unknown>) =>
    request('/api/nfo/item', 'PUT', { path, fields }),
  nfoBatch: (paths: string[], action: string, value: string) =>
    request<{ success: number; failed: { path: string; error: string }[] }>('/api/nfo/batch', 'POST', {
      paths,
      action,
      value,
    }),
  nfoDelete: (path: string) => request(`/api/nfo/item?path=${encodeURIComponent(path)}`, 'DELETE'),
  nfoRescrape: (path: string) => request(`/api/nfo/rescrape?path=${encodeURIComponent(path)}`, 'POST'),
  nfoCreate: (payload: {
    dir?: string
    subfolder?: string
    filename?: string
    overwrite?: boolean
    fields: Record<string, unknown>
  }) => request<{ ok: boolean; path: string; content: string }>('/api/nfo/create', 'POST', payload),
  nfoCreateCover: (name: string, dir: string, subfolder: string, file: File, overwrite = true) =>
    fetch(
      `/api/nfo/create-cover?name=${encodeURIComponent(name)}&dir=${encodeURIComponent(
        dir,
      )}&subfolder=${encodeURIComponent(subfolder)}&filename=${encodeURIComponent(file.name)}&overwrite=${overwrite}`,
      { method: 'POST', body: file },
    ).then(async (resp) => {
      if (!resp.ok) {
        let detail = resp.statusText
        try {
          detail = (await resp.json()).detail ?? detail
        } catch {
          /* keep statusText */
        }
        throw new Error(detail)
      }
      return resp.json() as Promise<{ ok: boolean; thumb: string; poster: string }>
    }),
  nfoMoveVideo: (src: string, dir: string, subfolder: string, name: string, overwrite: boolean) =>
    request<{ ok: boolean; path: string }>(
      `/api/nfo/move-video?src=${encodeURIComponent(src)}&dir=${encodeURIComponent(
        dir,
      )}&subfolder=${encodeURIComponent(subfolder)}&name=${encodeURIComponent(name)}&overwrite=${overwrite}`,
      'POST',
    ),
  extractNumber: (path: string) =>
    request<{ number: string }>(`/api/nfo/extract-number?path=${encodeURIComponent(path)}`),
  // ===== Emby 演员管理 =====
  embyTest: () => request<{ ok: boolean; folders: unknown[] }>('/api/emby/test', 'POST'),
  embyActors: (filterActorOnly = true) =>
    request<{ actors: EmbyActor[] }>(`/api/emby/actors?filter_actor_only=${filterActorOnly}`),
  embyActorDetail: (name: string) =>
    request<Record<string, any>>(`/api/emby/actor/detail?name=${encodeURIComponent(name)}`),
  embyActorUpdate: (actor: Record<string, unknown>, imagePath = '') =>
    request('/api/emby/actor/update', 'POST', { actor, image_path: imagePath }),
  embyActorUploadImage: (actor: Record<string, unknown>, imagePath: string) =>
    request('/api/emby/actor/upload-image', 'POST', { actor, image_path: imagePath }),
  actorsCache: () =>
    request<{ cached: boolean; ts: number; actors: EmbyActor[] }>('/api/emby/actors-cache'),
  saveActorsCache: (actors: EmbyActor[]) =>
    request<{ ok: boolean; ts: number }>('/api/emby/actors-cache', 'PUT', { actors }),
  embyActorUploadAvatarFile: (name: string, actorId: string, serverId: string, file: File) =>
    fetch(
      `/api/emby/actor/upload-image-file?name=${encodeURIComponent(name)}&actor_id=${encodeURIComponent(
        actorId,
      )}&server_id=${encodeURIComponent(serverId)}&filename=${encodeURIComponent(file.name)}`,
      { method: 'POST', body: file },
    ).then(async (resp) => {
      if (!resp.ok) {
        let detail = resp.statusText
        try {
          detail = (await resp.json()).detail ?? detail
        } catch {
          /* keep statusText */
        }
        throw new Error(detail)
      }
      return resp.json() as Promise<{ ok: boolean; message: string }>
    }),
  embyActorDeleteImage: (actor: Record<string, unknown>) =>
    request('/api/emby/actor/delete-image', 'POST', { actor }),
}

function apiBase(): string {
  return ''
}

export interface CacheFailedItem {
  file_path: string
  number: string
  fail_count: number
  error: string
  scraped_at: string
}

export interface NfoSummary {
  path: string
  dir: string
  file: string
  title: string
  number: string
  actor: string[]
  director: string
  series: string
  release: string
  has_poster: boolean
  has_thumb: boolean
}

export interface EmbyActor {
  name: string
  id?: string
  server_id?: string
  has_image?: boolean
  has_overview?: boolean
  movie_count?: number
}

export interface ScrapeStatus {
  state: string
  progress: number
  results: number
  counts: {
    succ: number
    fail: number
    done: number
    total: number
    skipped: number
    restored: number
    in_progress: number
  }
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
