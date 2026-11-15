/** 行程端点封装（GET/POST /trips、PATCH /trips/{id}/status、DELETE） */
import { request } from './client'

import type { components } from './schema'

type S = components['schemas']

export type TripPlanCard = S['TripPlanCard']
export type TripPlanIn = S['TripPlanIn']

/** 行程状态（对齐矩阵 F-2：05 最近足迹=status=done、07 日期轴=planned） */
export type TripStatus = 'planned' | 'done'

export async function listTrips(params?: { status?: TripStatus }): Promise<TripPlanCard[]> {
  return request<TripPlanCard[]>('/trips', { params })
}

/** POST /trips：AI 生成的计划卡直接落库 */
export async function createTrip(payload: TripPlanIn): Promise<TripPlanCard> {
  return request<TripPlanCard>('/trips', { method: 'POST', data: payload })
}

export async function getTrip(tripId: number | string): Promise<TripPlanCard> {
  return request<TripPlanCard>(`/trips/${tripId}`)
}

/** PATCH /trips/{id}/status：日期轴上的状态切换 */
export async function updateTripStatus(tripId: number | string, status: TripStatus): Promise<TripPlanCard> {
  return request<TripPlanCard>(`/trips/${tripId}/status`, { method: 'PATCH', data: { status } })
}

export async function deleteTrip(tripId: number | string): Promise<void> {
  await request<Record<string, never>>(`/trips/${tripId}`, { method: 'DELETE' })
}
