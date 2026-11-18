/**
 * M8 Task 4 · 游客模式统一拦截工具（guard）：
 * - 游客可自由浏览公开内容（路线库 / 路线详情；后端 GET /routes、GET /routes/{id}
 *   本就是公开端点，client.ts withAuth 在无 token 时跳过 Authorization 注入，
 *   游客请求直接 200，不会出现 401 错误卡）。
 * - 受限动作（AI 对话发送 / 生成计划 / 加入计划 / 行程 / 装备 / 画像）点击时统一
 *   requireAuth()：有 token 放行；无 token 弹 Taro.showModal（登录后可用 + 去登录 /
 *   逛逛），确认后 weapp 跳 wechat-login、H5 跳 login。
 * 统一交互组件化：所有接入点共用本模块的文案 / 配色 / 跳转口径，页面不得自弹自跳
 * （替换 M8 Task 3 及此前各页面散落的 toast+900ms reLaunch 登录写法）。
 */
import Taro from '@tarojs/taro'

import { getTokenPair, LOGIN_PAGE, WECHAT_LOGIN_PAGE } from './client'

/** 未登录确认后的去向：weapp 一键登录页 / H5 邮箱登录页 */
export function loginEntryUrl(): string {
  return process.env.TARO_ENV === 'weapp' ? WECHAT_LOGIN_PAGE : LOGIN_PAGE
}

/** 跳登录入口：navigateTo 保留浏览上下文；路由栈满或页面未注册时兜底 reLaunch */
export function goLoginEntry(): void {
  const url = loginEntryUrl()
  void Taro.navigateTo({ url }).catch(() => {
    void Taro.reLaunch({ url }).catch(() => undefined)
  })
}

/**
 * 受限动作守卫：true = 已登录，调用方继续执行原动作；
 * false = 游客，已弹出「登录后可用」模态（确认 = 去登录），调用方直接 return。
 * 同步返回布尔值以便接入点写成 `if (!requireAuth()) return` 的统一形态。
 */
export function requireAuth(): boolean {
  if (getTokenPair()) return true
  void Taro.showModal({
    title: '登录后可用',
    content: '该功能需要登录后使用',
    confirmText: '去登录',
    cancelText: '逛逛',
    confirmColor: '#a4f150',
  })
    .then((res) => {
      if (res.confirm) goLoginEntry()
    })
    .catch(() => undefined)
  return false
}
