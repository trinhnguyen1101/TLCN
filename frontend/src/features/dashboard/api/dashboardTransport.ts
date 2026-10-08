import type { DashboardData } from '../types'
import { queryErrorMessage } from '../model/presentation'

export interface LoadOptions { signal?: AbortSignal; force?: boolean }
export type DashboardLoader<T extends DashboardData = DashboardData> = (query: string, options?: LoadOptions) => Promise<T>

/** Bound memory, deduplicate subscribers and cancel work when the last view leaves. */
export function createDashboardLoader<T extends DashboardData>(endpoint: string, parse: (raw: unknown) => T, errorMessage: string): DashboardLoader<T> {
  const cache = new Map<string, { data: T; expires: number }>()
  const pending = new Map<string, { promise: Promise<T>; controller: AbortController; subscribers: Set<symbol>; cancel?: ReturnType<typeof setTimeout> }>()
  let generation: string | undefined
  return (query, options = {}) => {
    if (options.signal?.aborted) return Promise.reject(new DOMException('Yêu cầu đã bị hủy.', 'AbortError'))
    const params = new URLSearchParams(query)
    params.sort()
    const key = params.toString()
    const cached = cache.get(key)
    if (!options.force && cached && cached.expires > Date.now()) {
      cache.delete(key); cache.set(key, cached)
      return Promise.resolve(cached.data)
    }
    cache.delete(key)
    let request = pending.get(key)
    if (!request || request.controller.signal.aborted) {
      const controller = new AbortController()
      const timeout = params.get('resolution') === 'daily' ? 120_000 : 30_000
      const promise = fetch(`${endpoint}?${key}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(timeout)]) })
        .then(async (response) => {
          if (!response.ok) {
            if (response.status === 422) {
              const body = await response.json() as { detail: unknown }
              throw new Error(queryErrorMessage(body.detail))
            }
            throw new Error(errorMessage)
          }
          const data = parse(await response.json())
          if (data.metadata?.generation !== generation) { cache.clear(); generation = data.metadata?.generation }
          cache.set(key, { data, expires: Date.now() + 15_000 })
          let rows = [...cache.values()].reduce((count, entry) => count + entry.data.dashboardTrendRecords.length, 0)
          while (cache.size > 8 || rows > 60_000) {
            const oldest = cache.keys().next().value!
            rows -= cache.get(oldest)!.data.dashboardTrendRecords.length
            cache.delete(oldest)
          }
          return data
        }).catch((error: unknown) => {
          if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('Nguồn dữ liệu phản hồi quá lâu. Vui lòng thử lại hoặc chọn khoảng thời gian ngắn hơn.')
          if (error instanceof TypeError || error instanceof SyntaxError) throw new Error(errorMessage)
          throw error
        }).finally(() => { if (pending.get(key)?.controller === controller) pending.delete(key) })
      request = { promise, controller, subscribers: new Set() }
      pending.set(key, request)
    }
    clearTimeout(request.cancel)
    const current = request
    const token = Symbol()
    current.subscribers.add(token)
    return new Promise<T>((resolve, reject) => {
      const release = () => {
        options.signal?.removeEventListener('abort', abort)
        current.subscribers.delete(token)
        if (!current.subscribers.size && pending.get(key) === current) current.cancel = setTimeout(() => current.controller.abort(), 25)
      }
      const abort = () => { release(); reject(new DOMException('Yêu cầu đã bị hủy.', 'AbortError')) }
      options.signal?.addEventListener('abort', abort, { once: true })
      current.promise.then((data) => { release(); resolve(data) }, (error: unknown) => { release(); reject(error) })
    })
  }
}
