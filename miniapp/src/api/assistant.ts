/** AI 助手端点封装（chat POST SSE、plan、quota、sessions、memory） */
import { request, sse, type SseEvent, type SseHandle, type SseOptions } from './client'

import type { components } from './schema'

type S = components['schemas']

export type ChatIn = S['ChatIn']
export type PlanIn = S['PlanIn']
export type UsageOut = S['UsageOut']
export type TripPlanCard = S['TripPlanCard']

/** /assistant/sessions、/assistant/memory 后端契约是 loose dict 数组 */
export type AssistantSession = Record<string, unknown>
export type MemoryItem = Record<string, unknown>

/**
 * POST /assistant/chat —— POST SSE 事件流
 * （session / clarify / retrieve / cards / token / sources / done，见对齐矩阵 06 页）。
 * H5 返回 SseHandle（可 abort）；weapp 会抛 NotSupportedError。
 */
export function chat(payload: ChatIn, onEvent: (event: SseEvent) => void, opts?: SseOptions): SseHandle {
  return sse('/assistant/chat', payload, onEvent, opts)
}

/** POST /assistant/plan：槽位选线 → 生成计划卡 */
export async function generatePlan(payload: PlanIn): Promise<TripPlanCard> {
  return request<TripPlanCard>('/assistant/plan', { method: 'POST', data: payload })
}

/** GET /assistant/quota：用户侧配额（对齐矩阵 P0 G-1） */
export async function quota(): Promise<UsageOut> {
  return request<UsageOut>('/assistant/quota')
}

export async function listSessions(): Promise<AssistantSession[]> {
  return request<AssistantSession[]>('/assistant/sessions')
}

export async function listMemory(): Promise<MemoryItem[]> {
  return request<MemoryItem[]>('/assistant/memory')
}

export async function deleteMemory(memoryId: number | string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/assistant/memory/${memoryId}`, { method: 'DELETE' })
}
