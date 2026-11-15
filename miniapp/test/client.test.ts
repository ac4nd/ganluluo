/**
 * client.ts 纯逻辑回归测试（vitest + mock @tarojs/taro，Node 环境无 DOM 依赖）。
 * 重点回归 review Critical-1：401 刷新后的重试必须携带新 Bearer token；
 * 防循环用 _retried 独立标志，skipAuth 语义不变（不注入、不刷新）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TOKEN_KEY, request } from '../src/api/client'

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

interface ReqOpt {
  url: string
  method?: string
  data?: unknown
  header?: Record<string, string>
}
interface MockRes {
  statusCode: number
  data: unknown
}

const store: Record<string, unknown> = {}
const calls: ReqOpt[] = []

const OLD_PAIR = { access_token: 'old-a', refresh_token: 'r1', token_type: 'bearer' }
const NEW_PAIR = { access_token: 'new-a', refresh_token: 'r2', token_type: 'bearer' }

/** 按 url + 命中次数路由响应；未命中的 url 返回 500 便于发现问题 */
function respondBy(handler: (opt: ReqOpt, hit: number) => MockRes | undefined): void {
  const hits = new Map<string, number>()
  mocks.request.mockImplementation((opt: ReqOpt) => {
    calls.push(opt)
    const key = opt.url.replace(/^https?:\/\/[^/]+/, '')
    const hit = (hits.get(key) ?? 0) + 1
    hits.set(key, hit)
    const res = handler(opt, hit)
    if (res) return Promise.resolve(res)
    return Promise.resolve({ statusCode: 500, data: { detail: `unexpected ${key}` } })
  })
}

const refreshCalls = (): ReqOpt[] => calls.filter((c) => c.url.includes('/auth/refresh'))

beforeEach(() => {
  calls.length = 0
  for (const k of Object.keys(store)) delete store[k]
  store[TOKEN_KEY] = { ...OLD_PAIR }
  mocks.getStorageSync.mockImplementation((k: string) => store[k])
  mocks.setStorageSync.mockImplementation((k: string, v: unknown) => {
    store[k] = v
  })
  mocks.removeStorageSync.mockImplementation((k: string) => {
    delete store[k]
  })
  mocks.reLaunch.mockImplementation(() => Promise.resolve())
  mocks.request.mockReset()
})

describe('request：401 刷新与重试', () => {
  it('Critical-1 回归：401 → refresh 成功 → 重试请求携带新 Bearer token', async () => {
    respondBy((opt, hit) => {
      if (opt.url.endsWith('/trips')) {
        if (hit === 1) return { statusCode: 401, data: { detail: 'token expired' } }
        return { statusCode: 200, data: [{ id: 7 }] }
      }
      if (opt.url.endsWith('/auth/refresh')) {
        return { statusCode: 200, data: { ...NEW_PAIR } }
      }
      return undefined
    })

    const data = await request<{ id: number }[]>('/trips')
    expect(data).toEqual([{ id: 7 }])

    expect(calls).toHaveLength(3)
    // 首次：携带旧 token
    expect(calls[0].header?.Authorization).toBe('Bearer old-a')
    // 刷新：带 refresh_token，不注入 Bearer
    expect(calls[1].url).toContain('/auth/refresh')
    expect(calls[1].data).toEqual({ refresh_token: 'r1' })
    expect(calls[1].header?.Authorization).toBeUndefined()
    // 重试：必须携带刚换到的新 token（Critical-1：此前 skipAuth 抑制了注入）
    expect(calls[2].url).toContain('/trips')
    expect(calls[2].header?.Authorization).toBe('Bearer new-a')
    // 新 token 对已入库
    expect(store[TOKEN_KEY]).toMatchObject(NEW_PAIR)
  })

  it('重试最多一次：仍 401 直接抛错，不二次刷新', async () => {
    respondBy((opt) => {
      if (opt.url.endsWith('/auth/refresh')) return { statusCode: 200, data: { ...NEW_PAIR } }
      return { statusCode: 401, data: { detail: 'expired' } }
    })
    await expect(request('/trips')).rejects.toMatchObject({ status: 401 })
    expect(refreshCalls()).toHaveLength(1)
    expect(calls.filter((c) => c.url.includes('/trips'))).toHaveLength(2)
  })

  it('skipAuth：401 不触发刷新、不注入 Authorization（login/register/refresh 语义不变）', async () => {
    respondBy(() => ({ statusCode: 401, data: { detail: 'bad creds' } }))
    await expect(
      request('/auth/login', { method: 'POST', skipAuth: true }),
    ).rejects.toMatchObject({ status: 401, detail: 'bad creds' })
    expect(refreshCalls()).toHaveLength(0)
    expect(mocks.reLaunch).not.toHaveBeenCalled()
    expect(calls.every((c) => c.header?.Authorization === undefined)).toBe(true)
  })

  it('refresh 自身 401：清 storage + 跳 login，不重试原请求', async () => {
    respondBy((opt) => {
      if (opt.url.endsWith('/auth/refresh')) {
        return { statusCode: 401, data: { detail: 'refresh expired' } }
      }
      return { statusCode: 401, data: { detail: 'expired' } }
    })
    await expect(request('/trips')).rejects.toMatchObject({
      status: 401,
      // detail 透传后端原始文案（fallback 仅在后端无 detail 时生效）
      detail: 'refresh expired',
    })
    expect(mocks.removeStorageSync).toHaveBeenCalledWith(TOKEN_KEY)
    expect(mocks.reLaunch).toHaveBeenCalled()
    expect(calls).toHaveLength(2) // 原始 + refresh，无重试
  })

  it('并发 401 单飞：/auth/refresh 只调一次，重试都带新 token', async () => {
    respondBy((opt, hit) => {
      if (opt.url.endsWith('/auth/refresh')) {
        return { statusCode: 200, data: { ...NEW_PAIR } }
      }
      return hit === 1
        ? { statusCode: 401, data: { detail: 'expired' } }
        : { statusCode: 200, data: { ok: true } }
    })
    const [a, b] = await Promise.all([request('/a'), request('/b')])
    expect(a).toEqual({ ok: true })
    expect(b).toEqual({ ok: true })
    expect(refreshCalls()).toHaveLength(1)
    const retries = calls.filter(
      (c) => !c.url.includes('/auth/refresh') && c.header?.Authorization === 'Bearer new-a',
    )
    expect(retries).toHaveLength(2)
  })

  it('非 2xx 归一化错误：status/detail 透传（validation 数组取 msg）', async () => {
    respondBy(() => ({ statusCode: 422, data: { detail: [{ msg: 'field error' }] } }))
    await expect(request('/x')).rejects.toMatchObject({ status: 422, detail: 'field error' })
  })
})
