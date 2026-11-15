/** 路线库 / 轨迹端点封装（GET /routes、GET /routes/{id}、POST /tracks 等） */
import Taro from '@tarojs/taro'

import { apiBaseUrl, authHeaders, normalizeError, request } from './client'

import type { components } from './schema'

type S = components['schemas']

export type RouteOut = S['RouteOut']
export type RouteDetailOut = S['RouteDetailOut']
export type RouteIn = S['RouteIn']
export type TrackOut = S['TrackOut']
export type Sport = S['Sport']

/** GET /routes 的筛选参数（对齐矩阵 10 页：运动/难度≤N/轨迹清晰/地区或名称）。
 * 用 type alias 而非 interface：interface 无隐式索引签名，直接传 request()
 * 的 params（Record<string, ...>）会类型不兼容。 */
export type RouteListParams = {
  /** 关键词：region OR name 匹配（4fe5d69 新语义） */
  q?: string
  region?: string
  sport?: Sport
  difficulty_max?: number
  clarity?: boolean
}

export async function listRoutes(params?: RouteListParams): Promise<RouteOut[]> {
  return request<RouteOut[]>('/routes', { params })
}

export async function getRoute(routeId: number | string): Promise<RouteDetailOut> {
  return request<RouteDetailOut>(`/routes/${routeId}`)
}

export async function createRoute(payload: RouteIn): Promise<RouteOut> {
  return request<RouteOut>('/routes', { method: 'POST', data: payload })
}

/**
 * POST /tracks（multipart：name/region/sport + file），同步解析入库。
 * 走 Taro.uploadFile（JSON request() 不支持文件），错误归一化为 ApiError。
 */
export async function uploadTrack(file: {
  filePath: string
  /** 轨迹名（后端 minLength 1） */
  name: string
  region: string
  sport: Sport
}): Promise<TrackOut> {
  const res = await Taro.uploadFile({
    url: apiBaseUrl() + '/tracks',
    filePath: file.filePath,
    name: 'file',
    formData: { name: file.name, region: file.region, sport: file.sport },
    header: authHeaders(),
  })
  if (res.statusCode >= 200 && res.statusCode < 300) {
    try {
      return (typeof res.data === 'string' ? JSON.parse(res.data) : res.data) as TrackOut
    } catch {
      throw normalizeError(res.statusCode, undefined, '轨迹上传响应解析失败')
    }
  }
  let data: unknown
  try {
    data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
  } catch {
    /* 保留原始字符串 */
  }
  throw normalizeError(res.statusCode, data)
}
