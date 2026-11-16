/**
 * 类型化请求封装（全端共用）。
 *
 * baseURL 规则：
 * - 构建期常量 process.env.GL_API_BASE（config/index.ts defineConstants 注入，
 *   默认空串；可用 `GL_API_BASE=... npm run build:xxx` 覆盖）。
 * - H5 dev 默认空串 = 同源相对路径：config/index.ts h5.devServer.proxy 把后端
 *   路径（/ops /auth /assistant ...）转发到本地 uvicorn（127.0.0.1:8123）。
 *   注意后端 app/main.py 没有挂 CORS 中间件，浏览器直连 8123 会被跨域拦截，
 *   所以 H5 不能默认写绝对地址。
 * - weapp：Taro.request 必须绝对地址，默认直连本地 uvicorn；真机自测请用
 *   `GL_API_BASE=http://<局域网IP>:8123` 重新构建。
 */
import Taro from '@tarojs/taro'

import type { components } from './schema'

/* ---------- openapi 契约类型（components/schemas 出口） ---------- */
export type TokenPair = components['schemas']['TokenPair']
export type LoginIn = components['schemas']['LoginIn']
export type RegisterIn = components['schemas']['RegisterIn']
export type UserOut = components['schemas']['UserOut']
export type RefreshIn = components['schemas']['RefreshIn']

/** 本地存储 key：登录态双 token 存一个对象（TokenPair） */
export const TOKEN_KEY = 'gl_token_pair'
/** 首页入口（Task 2 起 index 页 = 入口/导航页） */
export const HOME_PAGE = '/pages/index/index'
/** 登录态彻底失效后的统一去向（login 页在 Task 2 注册进 app.config 后生效） */
export const LOGIN_PAGE = '/pages/login/index'
/** 引导流入口（M7.5：注册成功 → 02 运动偏好 → 03 经验体能 → 04 装备 → 首页） */
export const ONBOARD_SPORT_PAGE = '/pages/onboard/sport/index'
export const ONBOARD_EXP_PAGE = '/pages/onboard/exp/index'

const BASE_URL =
  process.env.GL_API_BASE ||
  (process.env.TARO_ENV === 'weapp' ? 'http://127.0.0.1:8123' : '')

/** dev/prod 同源部署时 BASE_URL 为空串可直接拼 path；诊断用 */
export const apiBaseUrl = (): string => BASE_URL

/* ---------- API 同源约束（SSRF 防护） ---------- */
/** 提取 scheme://host[:port] 小写串；无 scheme（H5 相对路径）原样返回。 */
function originOf(url: string): string {
  const i = url.indexOf('://')
  if (i === -1) return url
  const scheme = url.slice(0, i + 3).toLowerCase()
  const rest = url.slice(i + 3)
  let host = rest
  for (const ch of ['/', '?', '#']) {
    const pos = rest.indexOf(ch)
    if (pos !== -1 && pos < host.length) host = rest.slice(0, pos)
  }
  return scheme + host.toLowerCase()
}

const API_ORIGIN = originOf(BASE_URL)

/**
 * API 请求同源校验：url 必须是相对路径（H5 devServer 同源代理）或与构建期
 * API origin 一致。防 request() 的 opts.baseUrl 能力面被滥用为任意地址外发。
 * MinIO presign 直传不经本函数（media.ts 直连外部 upload_url，属对象存储
 * 业务设计）。
 */
export function assertApiOrigin(url: string): void {
  if (url.startsWith('/')) return
  const target = originOf(url)
  if (target !== API_ORIGIN) {
    throw normalizeError(0, undefined, '拒绝非 API 同源地址：' + target)
  }
}

/* ---------- 归一化错误 ---------- */
export interface ApiError {
  /** HTTP 状态码；0 = 网络层失败（断网/超时/请求未到达） */
  status: number
  /** 后端 detail 或可读文案 */
  detail: string
  /** 原始响应体（诊断用） */
  raw?: unknown
}

function msgOf(err: unknown): string {
  const e = err as { errMsg?: string; message?: string } | undefined
  return e?.errMsg || e?.message || String(err)
}

/** FastAPI 错误体 {detail: string | [{msg,loc...}]} → 归一化 detail 文案 */
export function normalizeError(status: number, data: unknown, fallback = '请求失败'): ApiError {
  let detail = fallback
  if (data && typeof data === 'object') {
    const d = (data as Record<string, unknown>).detail
    if (typeof d === 'string' && d) {
      detail = d
    } else if (Array.isArray(d)) {
      detail = d
        .map((x) => (typeof x === 'object' && x !== null && typeof (x as { msg?: unknown }).msg === 'string'
          ? (x as { msg: string }).msg
          : JSON.stringify(x)))
        .join('; ')
    } else if (d != null) {
      detail = JSON.stringify(d)
    } else {
      // slowapi 429 的 JSON 体是 {error: "..."}（main.py handler 原样透传）
      const r = data as Record<string, unknown>
      const m =
        typeof r.message === 'string' && r.message
          ? r.message
          : typeof r.error === 'string' && r.error
            ? r.error
            : ''
      if (m) detail = m
    }
  }
  return { status, detail, raw: data }
}

/* ---------- token 存取（auth.ts re-export 给页面用） ---------- */

export function getTokenPair(): TokenPair | null {
  try {
    const v = Taro.getStorageSync(TOKEN_KEY) as unknown
    if (v && typeof v === 'object' && typeof (v as TokenPair).access_token === 'string') {
      return v as TokenPair
    }
    return null
  } catch {
    return null
  }
}

export function setTokenPair(pair: TokenPair): void {
  Taro.setStorageSync(TOKEN_KEY, pair)
}

export function clearTokenPair(): void {
  try {
    Taro.removeStorageSync(TOKEN_KEY)
  } catch {
    /* storage 不可用时忽略 */
  }
}

/** 清登录态并跳登录页；login 页未注册（Task 2 前）时吞掉路由错误 */
export function redirectLogin(): void {
  clearTokenPair()
  void Taro.reLaunch({ url: LOGIN_PAGE }).catch(() => {
    /* login 页 Task 2 落地前路由不存在 */
  })
}

function withAuth(header: Record<string, string>): Record<string, string> {
  const pair = getTokenPair()
  if (pair?.access_token) header.Authorization = `Bearer ${pair.access_token}`
  return header
}

/** 供 uploadFile 等旁路 API 复用的鉴权头 */
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return withAuth({ ...extra })
}

/* ---------- request ---------- */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  /** GET query 参数（自行拼 URL，保证 H5 / weapp 行为一致） */
  params?: Record<string, string | number | boolean | undefined | null>
  /** 请求体（JSON 序列化） */
  data?: unknown
  header?: Record<string, string>
  /** true = 不带 Authorization 且 401 不触发刷新重试（login/register/refresh 用） */
  skipAuth?: boolean
  /** 单发覆盖 baseURL（如临时直连 8123 自测） */
  baseUrl?: string
  /** 内部防循环标志：401 刷新后重试时置 true，重试仍 401 直接抛错（勿手动传） */
  _retried?: boolean
}

function withQuery(path: string, params?: RequestOptions['params']): string {
  if (!params) return path
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&')
  if (!qs) return path
  return path + (path.includes('?') ? '&' : '?') + qs
}

/** Taro.request 结果里我们只依赖这两个字段（避免耦合其类型命名空间） */
interface RawResponse {
  statusCode: number
  data: unknown
}

/** 底层请求：不做 401 刷新（供 refresh 流程与 uploadFile 复用语义时注意） */
async function raw(path: string, opts: RequestOptions): Promise<RawResponse> {
  const url = (opts.baseUrl ?? BASE_URL) + withQuery(path, opts.params)
  assertApiOrigin(url)
  const header: Record<string, string> = { ...opts.header }
  if (opts.data !== undefined) header['Content-Type'] = header['Content-Type'] || 'application/json'
  if (!opts.skipAuth) withAuth(header)
  try {
    return await Taro.request({ url, method: opts.method ?? 'GET', data: opts.data, header })
  } catch (err) {
    // 网络层失败（断网/超时）：Taro.request promise reject
    throw normalizeError(0, undefined, `网络错误：${msgOf(err)}`)
  }
}

/* 401 单飞刷新：并发多个 401 只触发一次 /auth/refresh */
let refreshing: Promise<TokenPair> | null = null

async function doRefresh(): Promise<TokenPair> {
  const cur = getTokenPair()
  if (!cur?.refresh_token) {
    throw normalizeError(401, undefined, '登录态缺失，请重新登录')
  }
  let res: RawResponse
  try {
    // 刷新请求刻意不走 request()：不带业务 401 重试逻辑，避免循环
    assertApiOrigin(BASE_URL + '/auth/refresh')
    res = await Taro.request({
      url: BASE_URL + '/auth/refresh',
      method: 'POST',
      data: { refresh_token: cur.refresh_token },
      header: { 'Content-Type': 'application/json' },
    })
  } catch (err) {
    // 网络层失败：保留本地登录态、不跳转，直接抛给调用方
    throw normalizeError(0, undefined, `刷新登录态网络错误：${msgOf(err)}`)
  }
  if (res.statusCode >= 200 && res.statusCode < 300) {
    const pair = res.data as TokenPair
    setTokenPair(pair)
    return pair
  }
  // refresh 自己 401 = 双 token 均失效：清 storage → 跳 login（防循环终点）
  if (res.statusCode === 401) redirectLogin()
  throw normalizeError(res.statusCode, res.data, '登录已过期，请重新登录')
}

function refreshOnce(): Promise<TokenPair> {
  if (!refreshing) {
    refreshing = doRefresh().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

/**
 * 核心请求：非 2xx 抛 ApiError；401 时用 refresh_token 换新对并重试原请求一次。
 * 防循环用独立的 _retried 标志（重试仍 401 直接抛错，绝不二次刷新）；
 * 不能复用 skipAuth——那会同时抑制 Authorization 注入，导致重试请求
 * 不带新 token、必然再 401（review Critical-1，回归测试见 test/client.test.ts）。
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await raw(path, opts)
  if (res.statusCode >= 200 && res.statusCode < 300) return res.data as T
  if (res.statusCode === 401 && !opts.skipAuth && !opts._retried) {
    await refreshOnce()
    return request<T>(path, { ...opts, _retried: true })
  }
  throw normalizeError(res.statusCode, res.data)
}

/* ---------- ops ---------- */

/** GET /ops/health —— 轻端连通性自测（首页调试按钮用） */
export async function health(): Promise<Record<string, string>> {
  return request<Record<string, string>>('/ops/health', { skipAuth: true })
}

/* ---------- SSE（chat 是 POST SSE） ---------- */

export type SseEvent = Record<string, unknown>

export interface SseHandle {
  abort: () => void
}

export interface SseOptions {
  /** 外部 AbortSignal；缺省用内部 controller */
  signal?: AbortSignal
  /** 流式过程中的失败回调（主动 abort 不回调）；缺省 console.error */
  onError?: (err: ApiError) => void
}

/** weapp 端暂不支持的能力抛此错误 */
export class NotSupportedError extends Error {}

/**
 * POST SSE 流。H5：fetch + ReadableStream，按 SSE 规范以空行分帧、
 * 解析 "data: <JSON>" 行后回调 onEvent。
 * weapp：留接口，抛 NotSupportedError（Task 4 用 Taro.request enableChunked 实现）。
 */
export function sse(
  path: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
  opts: SseOptions = {},
): SseHandle {
  if (process.env.TARO_ENV !== 'h5') {
    throw new NotSupportedError('sse() 目前仅实现 H5（fetch 流式）；weapp 需 Taro.request enableChunked，Task 4 接入')
  }

  const controller = new AbortController()
  const handle: SseHandle = { abort: () => controller.abort() }

  void (async () => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }
    withAuth(headers)
    try {
      const res = await fetch(BASE_URL + path, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: opts.signal ?? controller.signal,
      })
      if (!res.ok) {
        let data: unknown
        try {
          data = await res.json()
        } catch {
          /* 非 JSON 错误体 */
        }
        throw normalizeError(res.status, data)
      }
      if (!res.body) {
        throw normalizeError(res.status, undefined, '响应缺少可读流（res.body 为空）')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const chunks = buf.split('\n\n')
        buf = chunks.pop() ?? ''
        for (const chunk of chunks) {
          for (const line of chunk.split(/\r?\n/)) {
            const text = line.trim()
            if (!text.startsWith('data:')) continue
            const payload = text.slice(5).trim()
            if (!payload || payload === '[DONE]') continue
            try {
              onEvent(JSON.parse(payload) as SseEvent)
            } catch {
              console.warn('[sse] 忽略非 JSON 事件:', payload)
            }
          }
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return // 主动中断不算错误
      const apiErr = (err as ApiError | undefined)?.status !== undefined
        ? (err as ApiError)
        : normalizeError(0, undefined, `SSE 失败：${msgOf(err)}`)
      if (opts.onError) opts.onError(apiErr)
      else console.error('[sse]', apiErr)
    }
  })()

  return handle
}
