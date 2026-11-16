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
  // 协议相对地址（//evil.com/x）会被浏览器按当前 scheme 补全成外部地址，
  // 不能当相对路径放行；originOf 对它取不到 scheme，走下方同源比对拒绝。
  if (url.startsWith('/') && !url.startsWith('//')) return
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

/**
 * SSE 分帧解析纯函数（H5 fetch 与 weapp onChunkReceived 双端共用）。
 * 输入：上一次的累积缓冲 + 新到达文本；输出：本次凑齐的完整事件数组 + 剩余缓冲。
 * 规则（SSE 规范子集，对齐后端 sse_frame `data: {json}\n\n`，见 assistant/router.py）：
 * - 按 \n 分行，最后一段不以 \n 结尾（半行/半事件）保留进 buffer 等下个 chunk；
 * - `data:` 前缀剥离（有无空格均可），行尾 \r 容错，非 data 行（event:/id:/注释）忽略；
 * - 空行 = 一帧结束：该帧累积的 data 按 JSON 解析后产出（解析失败整帧忽略不抛）；
 * - `data: [DONE]` 为流终止标志，不产出事件；
 * - 只消费到最后一个空行为止：其后未落地的行属于尚未闭合的帧，原样留在 buffer
 *   跨 chunk 持久（chunk 边界恰切在帧终止符 \n\n 两个 \n 之间时不丢帧）。
 */
export function feedSseChunk(buffer: string, text: string): { events: SseEvent[]; buffer: string } {
  const events: SseEvent[] = []
  const lines = (buffer + text).split('\n')
  const rest = lines.pop() ?? '' // 最后一段：以 \n 结尾时为空串，否则是半行
  // 找最后一个空行：其后的行（未闭合帧）不消费，原样回存 buffer
  let lastBlank = -1
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i] === '' || lines[i] === '\r') {
      lastBlank = i
      break
    }
  }
  let frame = '' // 当前帧累积的 data（多 data 行按 SSE 规范以 \n 合并）
  for (let i = 0; i <= lastBlank; i++) {
    const raw = lines[i]
    const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
    if (line === '') {
      // 空行分帧：攒齐的 data 落地
      if (frame) {
        try {
          events.push(JSON.parse(frame) as SseEvent)
        } catch {
          console.warn('[sse] 忽略非 JSON 事件:', frame)
        }
        frame = ''
      }
      continue
    }
    if (!line.startsWith('data:')) continue
    const piece = line.slice(5).trim()
    if (!piece || piece === '[DONE]') continue
    frame = frame ? `${frame}\n${piece}` : piece
  }
  // 未闭合帧的完整行原样回存（每行补回分行的 \n），与半行 rest 拼为下轮 buffer
  const open = lastBlank + 1 < lines.length ? lines.slice(lastBlank + 1).join('\n') + '\n' : ''
  return { events, buffer: open + rest }
}

/**
 * 流结束冲刷（H5 done / weapp success 共用语义）：把残余缓冲按完整行处理，
 * 再补一个空行触发分帧，让漏发末帧空行的服务端也能落地最后一个事件；
 * 传输中断导致的半行残帧会因 JSON 解析失败被忽略。正常流以空行收尾时
 * buffer 已为空，本函数是空操作。
 */
function flushSseBuffer(buffer: string, onEvent: (event: SseEvent) => void): void {
  if (!buffer) return
  const { events } = feedSseChunk(buffer, '\n\n')
  for (const ev of events) onEvent(ev)
}

/**
 * weapp 无 TextDecoder：手写 UTF-8 流式解码器（字符串拼接，无 eval/escape）。
 * onChunkReceived 的 chunk 边界可能切在多字节序列中间——按字节累积，不完整的
 * 序列留在 pendingBytes 等下一个 chunk 补齐后再解码；非法字节（非法首字节、
 * 坏续字节、代理区/越界码点）跳过不抛，保证脏数据不断流。
 */
export class Utf8StreamDecoder {
  private pendingBytes: number[] = []

  /** 解码一段字节，返回本次能安全解码的文本（不完整多字节序列留待下次） */
  decode(bytes: Uint8Array): string {
    const all = this.pendingBytes.length
      ? this.pendingBytes.concat(Array.from(bytes))
      : Array.from(bytes)
    this.pendingBytes = []
    let out = ''
    let i = 0
    while (i < all.length) {
      const b0 = all[i]
      // 首字节定序列长度；0xC0/0xC1（过长编码）与 0xF5+（越界/非字符）直接判非法
      let len = 0
      if (b0 < 0x80) len = 1
      else if (b0 >= 0xc2 && b0 <= 0xdf) len = 2
      else if (b0 >= 0xe0 && b0 <= 0xef) len = 3
      else if (b0 >= 0xf0 && b0 <= 0xf4) len = 4
      if (len === 0) {
        i += 1 // 非法首字节：跳过
        continue
      }
      if (i + len > all.length) {
        this.pendingBytes = all.slice(i) // 序列被 chunk 边界切断：缓冲至补齐
        break
      }
      let ok = true
      for (let j = 1; j < len; j++) {
        if ((all[i + j] & 0xc0) !== 0x80) {
          ok = false
          break
        }
      }
      if (!ok) {
        i += 1 // 坏续字节：丢弃首字节，其余字节按新序列重扫
        continue
      }
      let cp = b0
      if (len === 2) cp = ((b0 & 0x1f) << 6) | (all[i + 1] & 0x3f)
      else if (len === 3) cp = ((b0 & 0x0f) << 12) | ((all[i + 1] & 0x3f) << 6) | (all[i + 2] & 0x3f)
      else if (len === 4) {
        cp = ((b0 & 0x07) << 18) | ((all[i + 1] & 0x3f) << 12) | ((all[i + 2] & 0x3f) << 6) | (all[i + 3] & 0x3f)
      }
      if ((cp >= 0xd800 && cp <= 0xdfff) || cp > 0x10ffff) {
        i += len // 代理区 / 越界码点（如 F4 90 80 80 = 0x110000）：跳过整段，fromCodePoint 会抛
        continue
      }
      out += String.fromCodePoint(cp)
      i += len
    }
    return out
  }
}

/**
 * POST SSE 流（双端）：
 * - H5：fetch + ReadableStream，按 SSE 规范空行分帧后回调 onEvent；
 * - weapp：Taro.request enableChunked 分块流（基础库 >= 2.20.1），
 *   onChunkReceived 的 ArrayBuffer 经手写 UTF-8 解码后走同一解析器 feedSseChunk。
 * 返回可 abort 句柄；主动 abort 不触发 onError；外部 signal 可随时取消。
 */
export function sse(
  path: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
  opts: SseOptions = {},
): SseHandle {
  const url = BASE_URL + path
  assertApiOrigin(url)

  const controller = new AbortController()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  withAuth(headers)

  const reportError = (err: ApiError): void => {
    if (opts.onError) opts.onError(err)
    else console.error('[sse]', err)
  }

  if (process.env.TARO_ENV !== 'h5') {
    /* weapp 分支 */
    // Taro 的 weapp 运行时（@tarojs/shared getNormalRequest）把原生 RequestTask 的
    // abort/onChunkReceived 等方法挂到返回的 Promise 上（equipTaskMethodsIntoPromise），
    // 与 RequestTask<T> 类型签名一致，直接按该类型使用，无需断言。
    let task: ReturnType<typeof Taro.request> | null = null
    const handle: SseHandle = {
      abort: () => {
        controller.abort()
        task?.abort()
      },
    }
    const decoder = new Utf8StreamDecoder()
    let buf = ''
    const onChunk = (res: { data: ArrayBuffer }): void => {
      const parsed = feedSseChunk(buf, decoder.decode(new Uint8Array(res.data)))
      buf = parsed.buffer
      for (const ev of parsed.events) onEvent(ev)
    }
    task = Taro.request({
      url,
      method: 'POST',
      enableChunked: true,
      header: headers,
      data: body,
      success: (res) => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          // 非流式错误响应（401/429 等）：对齐 H5 的 !res.ok 分支；
          // chunked 模式下普通（非 chunked）错误体仍会在 success 里带 data
          reportError(normalizeError(res.statusCode, res.data, 'SSE 请求失败'))
          return
        }
        // 流正常结束：与 H5 done 清理一致，冲刷残余完整行（正常流以空行收尾时为空操作）
        flushSseBuffer(buf, onEvent)
      },
      fail: (res) => {
        if (controller.signal.aborted) return // abort 引起的 fail 不回调（对齐 H5）
        reportError(normalizeError(0, undefined, `SSE 失败：${msgOf(res)}`))
      },
    })
    task.onChunkReceived(onChunk)
    void task.catch(() => {
      /* 失败已由 fail 回调处理，这里只吞掉 Promise rejection 防未处理告警 */
    })
    if (controller.signal.aborted) task.abort() // 请求建立前就已 abort 的兜底
    if (opts.signal) {
      if (opts.signal.aborted) handle.abort()
      else opts.signal.addEventListener('abort', () => handle.abort(), { once: true })
    }
    return handle
  }

  /* H5 分支：fetch + ReadableStream（行为与既有实现一致，仅解析改走 feedSseChunk） */
  void (async () => {
    try {
      const res = await fetch(url, {
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
        const parsed = feedSseChunk(buf, decoder.decode(value, { stream: true }))
        buf = parsed.buffer
        for (const ev of parsed.events) onEvent(ev)
      }
      // 与 weapp success 清理一致：冲刷残余完整行（正常流以空行收尾时为空操作）
      flushSseBuffer(buf, onEvent)
    } catch (err) {
      if (controller.signal.aborted) return // 主动中断不算错误
      const apiErr = (err as ApiError | undefined)?.status !== undefined
        ? (err as ApiError)
        : normalizeError(0, undefined, `SSE 失败：${msgOf(err)}`)
      reportError(apiErr)
    }
  })()

  return { abort: () => controller.abort() }
}
