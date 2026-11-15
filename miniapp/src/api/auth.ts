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
