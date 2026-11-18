/**
 * 登录态端点封装：login / register / logout / me。
 * token 存取（getTokenPair/setTokenPair/clearTokenPair/redirectLogin）实现在
 * client.ts —— request() 的 401 刷新逻辑也要用，放那边避免循环依赖；这里
 * re-export 供页面统一从 api/auth 取用。
 */
import {
  request,
  setTokenPair,
  getTokenPair,
  clearTokenPair,
  redirectLogin,
  type TokenPair,
} from './client'

import type { components } from './schema'

type S = components['schemas']

export type LoginIn = S['LoginIn']
export type RegisterIn = S['RegisterIn']
export type RefreshIn = S['RefreshIn']
export type UserOut = S['UserOut']
export type LogoutOut = S['LogoutOut']

/**
 * 微信一键登录请求体（M8 Task 1 后端 d999327 已落 WechatLoginIn，但
 * backend/openapi.json 尚未重导出，先本地定义保持一致：code 1..128、
 * nickname ≤32 字可空）。
 */
export interface WechatLoginIn {
  /** wx.login() 取到的临时登录凭证 code */
  code: string
  /** 可选昵称；缺省后端用「徒步者 + 4 位随机数字」 */
  nickname?: string
}

export {
  /** 读本地登录态（TokenPair | null） */
  getTokenPair,
  /** 写本地登录态 */
  setTokenPair,
  /** 清本地登录态 */
  clearTokenPair,
  /** 清登录态并跳登录页 */
  redirectLogin,
}
export type { TokenPair }

/** POST /auth/login：成功即把 TokenPair 写入 storage */
export async function login(payload: LoginIn): Promise<TokenPair> {
  const pair = await request<TokenPair>('/auth/login', { method: 'POST', data: payload, skipAuth: true })
  setTokenPair(pair)
  return pair
}

/** POST /auth/register：注册即返回用户（不自动登录，登录态以 login 为准） */
export async function register(payload: RegisterIn): Promise<UserOut> {
  return request<UserOut>('/auth/register', { method: 'POST', data: payload, skipAuth: true })
}

/** POST /auth/refresh：显式换新 token 对（client 内部 401 也会自动走这条链路） */
export async function refresh(payload: RefreshIn): Promise<TokenPair> {
  return request<TokenPair>('/auth/refresh', { method: 'POST', data: payload, skipAuth: true })
}

/**
 * POST /auth/wechat-login：微信一键登录（M8 Task 2）。
 * wx.login() code 换 TokenPair；成功即写登录态（同 login 口径）。
 * 后端语义：dev 未配置微信凭据时走确定性 mock（同 code 同账号），
 * 401 微信失败/登录态缺失、403 disabled、502 上游不可达、503 prod 未配置。
 */
export async function wechatLogin(code: string, nickname?: string): Promise<TokenPair> {
  const payload: WechatLoginIn = nickname ? { code, nickname } : { code }
  const pair = await request<TokenPair>('/auth/wechat-login', {
    method: 'POST',
    data: payload,
    skipAuth: true,
  })
  setTokenPair(pair)
  return pair
}

/** GET /auth/me：当前用户 */
export async function me(): Promise<UserOut> {
  return request<UserOut>('/auth/me')
}

/** POST /auth/logout：吊销服务端 refresh_token；无论成败本地一律清登录态 */
export async function logout(): Promise<void> {
  try {
    const cur = getTokenPair()
    if (cur?.refresh_token) {
      await request<LogoutOut>('/auth/logout', {
        method: 'POST',
        data: { refresh_token: cur.refresh_token },
      })
    }
  } finally {
    clearTokenPair()
  }
}
