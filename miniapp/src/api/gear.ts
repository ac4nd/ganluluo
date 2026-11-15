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
