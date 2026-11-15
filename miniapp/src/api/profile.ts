/**
 * 用户画像端点封装：GET/PUT /profile（sports 多选 + exp_level 1-4 + fitness 1-5）。
 * 后端注册即建默认画像（sports=[] exp_level=1 fitness=2），GET 永远有值。
 */
import { request } from './client'

import type { components } from './schema'

type S = components['schemas']

export type ProfileIn = S['ProfileIn']
export type ProfileOut = S['ProfileOut']
export type Sport = S['Sport']

/** 8 类运动（Sport 枚举的展示元数据，label/sub 对齐原型 02-onboard-sport；轻端用 emoji 代原型 SVG 图标） */
export const SPORTS: { key: Sport; label: string; sub: string; emoji: string }[] = [
  { key: 'hiking', label: '徒步', sub: '山野长距离行走', emoji: '🥾' },
  { key: 'trail-running', label: '越野跑', sub: '山地越野奔跑', emoji: '🏃' },
  { key: 'climbing', label: '攀岩', sub: '岩壁与抱石', emoji: '🧗' },
  { key: 'stream', label: '溯溪', sub: '溪谷逆流而上', emoji: '🏞️' },
  { key: 'cycling', label: '骑行', sub: '山地 / 公路', emoji: '🚴' },
  { key: 'camping', label: '露营', sub: '过夜扎营体验', emoji: '⛺' },
  { key: 'skiing', label: '滑雪', sub: '雪道与野雪', emoji: '🎿' },
  { key: 'orienteering', label: '定向越野', sub: '持图打卡寻点', emoji: '🧭' },
]

/** 经验 1-4（对齐原型 03-onboard-exp 文案） */
export const EXP_LEVELS: { value: number; label: string; sub: string }[] = [
  { value: 1, label: '新手小白', sub: '1 年以内 / 完成徒步少于 5 次' },
  { value: 2, label: '初级玩家', sub: '1-3 年 / 走过成熟景区步道与小环线' },
  { value: 3, label: '进阶玩家', sub: '3-5 年 / 完成过 1000m 爬升的一日线' },
  { value: 4, label: '资深 / 领队', sub: '5 年以上 / 重装多日穿越与野外应急' },
]

/** 体能 1-5（对齐原型 03-onboard-exp 文案） */
export const FITNESS_LEVELS: { value: number; label: string; sub: string }[] = [
  { value: 1, label: '轻松休闲', sub: '每周运动 0-1 次，连续爬坡 30 分钟会明显气喘' },
  { value: 2, label: '一般', sub: '每周运动 1-2 次，可完成 8km / 爬升 400m 以内' },
  { value: 3, label: '良好', sub: '每周运动 3-4 次，可完成 15km / 爬升 1000m 一日线' },
  { value: 4, label: '强健', sub: '每周运动 5 次以上，20km+ 重装线无压力' },
  { value: 5, label: '运动员级', sub: '长期系统训练，可完成百公里越野赛事' },
]

/** GET /profile：当前画像 */
export function getProfile(): Promise<ProfileOut> {
  return request<ProfileOut>('/profile')
}

/** PUT /profile：整体覆盖保存（ProfileIn 三字段必传，做成一次批量提交） */
export function putProfile(payload: ProfileIn): Promise<ProfileOut> {
  return request<ProfileOut>('/profile', { method: 'PUT', data: payload })
}
