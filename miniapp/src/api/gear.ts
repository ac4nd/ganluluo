/**
 * 装备清单端点封装：/gear/catalog（公开）+ /gear-list（登录态读写）。
 * catalog 后端返回 loose dict（openapi 未定型），这里按 backend gear_service
 * 的实际返回形状收窄类型：{ categories:[{key,label}], items:[{key,label,category,models:[...]}] }。
 */
import { request } from './client'

import type { components } from './schema'

type S = components['schemas']

export type GearItemIn = S['GearItemIn']
export type GearItemOut = S['GearItemOut']

export interface GearCategory {
  key: string
  label: string
}

export interface GearModelOut {
  id: number
  brand: string
  model: string
  spec: string
}

export interface GearCatalogItem {
  key: string
  label: string
  category: string
  models: GearModelOut[]
}

export interface GearCatalog {
  categories: GearCategory[]
  items: GearCatalogItem[]
}

/** GET /gear/catalog：类目 → 装备项 → 型号 三级（公开端点，无需登录） */
export function getCatalog(): Promise<GearCatalog> {
  return request<GearCatalog>('/gear/catalog', { skipAuth: true })
}

/** GET /gear-list：我的装备勾选（item_key + model_id + custom_name） */
export function getGearList(): Promise<GearItemOut[]> {
  return request<GearItemOut[]>('/gear-list')
}

/** PUT /gear-list：整体覆盖保存（后端先全量校验再替换，重复条目 422） */
export function putGearList(items: GearItemIn[]): Promise<GearItemOut[]> {
  return request<GearItemOut[]>('/gear-list', { method: 'PUT', data: { items } })
}

/* ---------- M7.5 多型号勾选态（纯函数，test/gear-selection.test.ts 覆盖） ---------- */

/**
 * 单个装备项的本地勾选态（完整版：同 item 可勾多个型号，各生成一条
 * {item_key, model_id} 记录；custom_name 自定义一条（model_id=null）；
 * bare 兼容 MVP 老数据的「只勾 item 不选型号」条目（model_id=null, custom_name=null）。
 * 后端 UNIQUE(item_key, model_id)：同 item 的 custom 与 bare 都占 (item,null)，
 * 两者互斥——custom 非空时 bare 不出条目（见 payloadFromSel）。
 */
export interface GearItemSel {
  /** 已勾选的型号 id（可多个，顺序无关） */
  models: number[]
  /** 自定义名称（空串 = 未填） */
  custom: string
  /** 无型号裸标记（MVP 老数据回显 / gck 快捷勾选） */
  bare: boolean
}

/** item_key → 勾选态 */
export type GearSelMap = Record<string, GearItemSel>

/** GET /gear-list rows → 本地勾选态（同 item 多条 model 行聚合；空白 custom 视为裸标记） */
export function selFromRows(rows: GearItemOut[]): GearSelMap {
  const next: GearSelMap = {}
  for (const r of rows) {
    const cur: GearItemSel = next[r.item_key] ?? { models: [], custom: '', bare: false }
    const custom = r.custom_name?.trim() ?? ''
    if (r.model_id != null && !cur.models.includes(r.model_id)) cur.models.push(r.model_id)
    if (custom) cur.custom = custom
    if (r.model_id == null && !custom) cur.bare = true
    next[r.item_key] = cur
  }
  return next
}

/** 单 item 的落库条数（= 该 item 在 PUT payload 里的条数，用于计数联动） */
export function itemRowCount(sel: GearItemSel | undefined): number {
  if (!sel) return 0
  let n = sel.models.length
  if (sel.custom) n += 1
  else if (sel.bare && sel.models.length === 0) n += 1
  return n
}

/** 本地勾选态 → PUT /gear-list payload（同 item 多型号多条；custom 压掉 bare 防 (item,null) 撞 UNIQUE） */
export function payloadFromSel(sel: GearSelMap): GearItemIn[] {
  const items: GearItemIn[] = []
  for (const [item_key, s] of Object.entries(sel)) {
    for (const model_id of s.models) items.push({ item_key, model_id })
    if (s.custom) items.push({ item_key, model_id: null, custom_name: s.custom })
    else if (s.bare && s.models.length === 0) items.push({ item_key, model_id: null, custom_name: null })
  }
  return items
}
