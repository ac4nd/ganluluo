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
  /** 关键词：region OR name 匹配（4fe5d69 新语义；后端参数名就叫 region） */
  region?: string
  sport?: Sport
  difficulty_max?: number
  /** 后端 clarity: str（'high'/'mid'/'low'），「轨迹清晰」chip 传 'high' */
  clarity?: string
}

export async function listRoutes(params?: RouteListParams): Promise<RouteOut[]> {
  return request<RouteOut[]>('/routes', { params })
}

/* ---------- RouteDetailOut loose dict 字段的窄型 + 归一（对齐后端实际形状） ----------
 * schema.d.ts 里 elevation/pace/terrain/track_points 都是 {[key:string]:unknown}[]
 * （后端 pydantic list[dict]），页面按下列形状消费：
 * - elevation: [{km, m}]   —— 种子直接给；轨迹上传后由 points_to_elevation_profile 生成
 * - pace:      [{km, pace}]（配速 min/km）
 * - terrain:   [{type, pct}]
 * - track_points: [{lat, lon, ele}]（≤500 点，ele 可为 null；未上传轨迹为 null） */

export type ElevPoint = { km: number; m: number }
export type PacePoint = { km: number; pace: number }
export type TerrainSeg = { type: string; pct: number }
export type TrackPoint = { lat: number; lon: number; ele: number | null }

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

function pickNum(d: Record<string, unknown>, key: string): number | null {
  return isNum(d[key]) ? (d[key] as number) : null
}

export function asElevation(rows: RouteDetailOut['elevation']): ElevPoint[] {
  return rows
    .map((d) => ({ km: pickNum(d, 'km'), m: pickNum(d, 'm') }))
    .filter((p): p is ElevPoint => p.km !== null && p.m !== null)
    .sort((a, b) => a.km - b.km)
}

export function asPace(rows: RouteDetailOut['pace']): PacePoint[] {
  return rows
    .map((d) => ({ km: pickNum(d, 'km'), pace: pickNum(d, 'pace') }))
    .filter((p): p is PacePoint => p.km !== null && p.pace !== null)
    .sort((a, b) => a.km - b.km)
}

export function asTerrain(rows: RouteDetailOut['terrain']): TerrainSeg[] {
  return rows
    .map((d) => ({ type: typeof d.type === 'string' ? d.type : '', pct: pickNum(d, 'pct') }))
    .filter((p): p is TerrainSeg => p.type !== '' && p.pct !== null)
}

export function asTrackPoints(rows: RouteDetailOut['track_points']): TrackPoint[] {
  return (rows ?? [])
    .map((d) => ({ lat: pickNum(d, 'lat'), lon: pickNum(d, 'lon'), ele: pickNum(d, 'ele') }))
    .filter((p): p is TrackPoint => p.lat !== null && p.lon !== null)
}

/** 相邻轨迹点累计里程（haversine，km；与后端 geo.haversine_m 同公式，用于轨迹 ele 曲线 x 轴） */
export function trackCumKm(points: TrackPoint[]): number[] {
  const out: number[] = [0]
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]
    const b = points[i]
    const R = 6371000
    const rad = Math.PI / 180
    const dLat = (b.lat - a.lat) * rad
    const dLon = (b.lon - a.lon) * rad
    const s =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2
    out.push(out[i - 1] + (2 * R * Math.asin(Math.sqrt(s))) / 1000)
  }
  return out
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
