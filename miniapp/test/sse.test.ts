/**
 * sse() 双端回归测试（vitest + mock @tarojs/taro，Node 环境）。
 * 覆盖三关键解析用例（chunk 切断 data 行中段 / 单 chunk 多事件 / 中文 UTF-8
 * 跨 chunk 边界字节级切分）+ weapp enableChunked happy path / abort / fail /
 * 非 2xx + assertApiOrigin 协议相对 URL 拒绝 + H5 fetch 分支共用解析器回归。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  TOKEN_KEY,
  assertApiOrigin,
  feedSseChunk,
  sse,
  Utf8StreamDecoder,
  type SseEvent,
} from '../src/api/client'

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
  removeStorageSync: vi.fn(),
  reLaunch: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: {
    request: mocks.request,
    getStorageSync: mocks.getStorageSync,
    setStorageSync: mocks.setStorageSync,
    removeStorageSync: mocks.removeStorageSync,
    reLaunch: mocks.reLaunch,
  },
}))

const TOKEN = { access_token: 'a-1', refresh_token: 'r-1', token_type: 'bearer' }
const store: Record<string, unknown> = {}
const encoder = new TextEncoder()

/** sse() 传给 Taro.request 的参数形状（我们只依赖的字段） */
interface SseReqOpt {
  url: string
  method?: string
  enableChunked?: boolean
  header?: Record<string, string>
  data?: unknown
  success?: (res: { statusCode: number; data?: unknown }) => void
  fail?: (res: { errMsg?: string }) => void
}

/**
 * weapp RequestTask 替身：sse() 侧依赖 abort / onChunkReceived / catch 三个
 * 成员（Taro weapp 运行时把 RequestTask 方法挂到返回的 Promise 上）。
 */
class FakeTask {
  opt: SseReqOpt | null = null
  chunkCb: ((res: { data: ArrayBuffer }) => void) | null = null
  abort = vi.fn(() => {
    this.aborted = true
  })
  aborted = false

  onChunkReceived(cb: (res: { data: ArrayBuffer }) => void): void {
    this.chunkCb = cb
  }

  /* Promise 接口面：sse() 调 catch 吞 rejection，直接返回自身即可 */
  catch(_onRejected?: (reason: unknown) => void): FakeTask {
    return this
  }

  /** 模拟 onChunkReceived：文本 → ArrayBuffer（拷贝进独立 buffer 模拟底层分片） */
  emit(text: string): void {
    this.emitBytes(encoder.encode(text))
  }

  /** 模拟 onChunkReceived：直接给字节（UTF-8 跨 chunk 边界用例需要字节级切分） */
  emitBytes(bytes: Uint8Array): void {
    const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
    this.chunkCb?.({ data: ab })
  }

  finish(statusCode: number, data?: unknown): void {
    this.opt?.success?.({ statusCode, data })
  }

  failWith(errMsg: string): void {
    this.opt?.fail?.({ errMsg })
  }
}

const tasks: FakeTask[] = []

const lastTask = (): FakeTask => {
  expect(tasks.length).toBeGreaterThan(0)
  return tasks[tasks.length - 1]
}

const PREV_TARO_ENV = process.env.TARO_ENV

beforeEach(() => {
  tasks.length = 0
  store[TOKEN_KEY] = { ...TOKEN }
  mocks.getStorageSync.mockImplementation((k: string) => store[k])
  mocks.request.mockReset()
  mocks.request.mockImplementation((opt: SseReqOpt) => {
    const t = new FakeTask()
    t.opt = opt
    tasks.push(t)
    return t
  })
})

afterEach(() => {
  if (PREV_TARO_ENV === undefined) delete process.env.TARO_ENV
  else process.env.TARO_ENV = PREV_TARO_ENV
  vi.unstubAllGlobals()
})

describe('feedSseChunk：分帧解析纯函数', () => {
  it('关键用例 1：chunk 切断 data: 行中段，两半拼接后事件完整、半行留 buffer', () => {
    const first = feedSseChunk('', 'data: {"i":')
    expect(first.events).toEqual([])
    expect(first.buffer).toBe('data: {"i":')

    const second = feedSseChunk(first.buffer, '1}\n\ndata: [DONE]\n\n')
    expect(second.events).toEqual([{ i: 1 }]) // [DONE] 是终止标志，不产出事件
    expect(second.buffer).toBe('')
  })

  it('关键用例 2：单 chunk 多事件一次产出；坏 JSON 整帧忽略不断流', () => {
    const r1 = feedSseChunk('', 'data: {"i":1}\n\ndata: {"i":2}\n\ndata: {"bad"}\n\ndata: {"i":3}\n\n')
    expect(r1.events).toEqual([{ i: 1 }, { i: 2 }, { i: 3 }])
    expect(r1.buffer).toBe('')

    // 尾部半行保留；data: 前缀有无空格均可；非 data 行（event:/注释）忽略
    const r2 = feedSseChunk('', 'event: token\n: keep-alive\ndata:{"i":4}\n\ndata: {"i":')
    expect(r2.events).toEqual([{ i: 4 }])
    expect(r2.buffer).toBe('data: {"i":')
  })

  it('流结束冲刷：残余完整行（帧无空行收尾）落地为事件，换行符只结束半行', () => {
    // 仅补换行：data 行变完整但帧未闭合，不产出（严格 SSE 分帧语义）
    const mid = feedSseChunk('data: {"i":9}', '\n')
    expect(mid.events).toEqual([])
    expect(mid.buffer).toBe('')
    // 冲刷语义（client.ts flushSseBuffer）：补换行 + 空行触发分帧 → 落地
    const tail = feedSseChunk('data: {"i":9}', '\n\n')
    expect(tail.events).toEqual([{ i: 9 }])
    expect(tail.buffer).toBe('')
  })
})

describe('Utf8StreamDecoder：手写 UTF-8 解码', () => {
  it('多字节序列跨 chunk 边界：按字节缓冲至补齐后正确解码中文', () => {
    const dec = new Utf8StreamDecoder()
    const bytes = encoder.encode('你好')
    expect(dec.decode(bytes.slice(0, 1))).toBe('') // '你' 首字节 E4 不完整 → 全部缓冲
    expect(dec.decode(bytes.slice(1))).toBe('你好') // 补齐后一并解出
  })

  it('非法字节跳过不抛：脏数据不断流', () => {
    const dec = new Utf8StreamDecoder()
    expect(dec.decode(new Uint8Array([0xff, 0x41]))).toBe('A') // 非法首字节后跟 ASCII
    expect(dec.decode(encoder.encode('好'))).toBe('好') // 解码器状态未被污染
  })
})

describe('sse() weapp 分支（Taro.request enableChunked）', () => {
  beforeEach(() => {
    process.env.TARO_ENV = 'weapp'
  })

  it('关键用例 3：中文 UTF-8 跨 chunk 边界（字节级切分两个 onChunkReceived）', () => {
    const events: SseEvent[] = []
    sse('/assistant/chat', { message: '你好' }, (e) => events.push(e))
    const task = lastTask()

    // 请求参数：enableChunked + POST + 鉴权/Accept 头（base URL 为空串=相对路径）
    expect(task.opt?.enableChunked).toBe(true)
    expect(task.opt?.method).toBe('POST')
    expect(task.opt?.url).toBe('/assistant/chat')
    expect(task.opt?.header?.Authorization).toBe('Bearer a-1')
    expect(task.opt?.header?.Accept).toBe('text/event-stream')

    // 含中文的 JSON 行按字节切成两半：切点落在 '你'(E4 BD A0) 的首字节之后
    const line = 'data: {"text":"你好赶路"}\n\n'
    const bytes = encoder.encode(line)
    expect(encoder.encode('data: {"text":"').length).toBe(15) // ASCII 前缀 15 字节
    task.emitBytes(bytes.slice(0, 16)) // 15 + '你' 的 E4 → 半个字符 + 半行
    expect(events).toEqual([]) // 帧未闭合，不产出
    task.emitBytes(bytes.slice(16))
    expect(events).toEqual([{ text: '你好赶路' }])

    // 流正常结束（success 2xx）：冲刷残余，无多余事件
    task.finish(200)
    expect(events).toEqual([{ text: '你好赶路' }])
  })

  it('abort：task.abort() 被调，且 abort 引起的 fail 不回调 onError（对齐 H5）', () => {
    const onError = vi.fn()
    const handle = sse('/assistant/chat', {}, () => {}, { onError })
    const task = lastTask()
    handle.abort()
    expect(task.abort).toHaveBeenCalled()
    task.failWith('request:fail abort')
    expect(onError).not.toHaveBeenCalled()
  })

  it('外部 signal：abort 时联动 task.abort()', () => {
    const controller = new AbortController()
    sse('/assistant/chat', {}, () => {}, { signal: controller.signal })
    const task = lastTask()
    controller.abort()
    expect(task.abort).toHaveBeenCalled()
  })

  it('fail（非 abort）：onError 收到归一化网络错误 status=0', () => {
    const onError = vi.fn()
    sse('/assistant/chat', {}, () => {}, { onError })
    lastTask().failWith('request:fail timeout')
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ status: 0, detail: 'SSE 失败：request:fail timeout' }),
    )
  })

  it('success 非 2xx：对齐 H5 !res.ok 分支，onError 透传 statusCode/detail', () => {
    const onError = vi.fn()
    sse('/assistant/chat', {}, () => {}, { onError })
    lastTask().finish(401, { detail: 'token expired' })
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ status: 401, detail: 'token expired' }),
    )
  })
})

describe('sse() H5 分支：fetch + ReadableStream 共用解析器（行为不变）', () => {
  it('跨 chunk 断行 + 单流多事件 + [DONE] 不产出', async () => {
    process.env.TARO_ENV = 'h5'
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          // 在 'data:' 行中段切断，验证 H5 侧同样跨 chunk 缓冲
          controller.enqueue(encoder.encode('data: {"i":1}\n\nda'))
          controller.enqueue(encoder.encode('ta: {"i":2}\n\ndata: [DONE]\n\n'))
          controller.close()
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const events: SseEvent[] = []
    sse('/assistant/chat', { message: 'hi' }, (e) => events.push(e))
    await vi.waitFor(() => expect(events).toEqual([{ i: 1 }, { i: 2 }]))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/assistant/chat')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ message: 'hi' }))
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer a-1')
  })
})

describe('assertApiOrigin：同源约束', () => {
  /** assertApiOrigin 抛的是 ApiError 对象（非 Error 实例），用 try/catch 断言字段 */
  function catchApiError(fn: () => void): { status?: number; detail?: string } {
    try {
      fn()
    } catch (e) {
      return (e ?? {}) as { status?: number; detail?: string }
    }
    return {}
  }

  it('协议相对 URL（//evil.com/x）拒绝：不能当相对路径放行', () => {
    const err = catchApiError(() => assertApiOrigin('//evil.com/x'))
    expect(err.status).toBe(0)
    expect(err.detail).toContain('拒绝非 API 同源地址')
    // 相对路径仍然放行（H5 devServer 同源代理）
    expect(() => assertApiOrigin('/assistant/chat')).not.toThrow()
  })

  it('sse() 对非法地址同步抛 ApiError，不发起请求', () => {
    process.env.TARO_ENV = 'weapp'
    const err = catchApiError(() => sse('//evil.com/x', {}, () => {}))
    expect(err.detail).toContain('拒绝非 API 同源地址')
    expect(tasks.length).toBe(0)
  })
})
