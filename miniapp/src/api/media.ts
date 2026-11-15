/** 媒体端点封装（presign → 直传对象存储 → register → 取阅） */
import { request } from './client'

import type { components } from './schema'

type S = components['schemas']

export type PresignIn = S['PresignIn']
export type PresignOut = S['PresignOut']
export type MediaRegisterIn = S['MediaRegisterIn']
export type MediaRegisteredOut = S['MediaRegisteredOut']
export type MediaOut = S['MediaOut']
export type MediaUrlOut = S['MediaUrlOut']

/** POST /media/presign：拿直传 upload_url + object_key */
export async function presign(payload: PresignIn): Promise<PresignOut> {
  return request<PresignOut>('/media/presign', { method: 'POST', data: payload })
}

/**
 * 用 presign 的 upload_url 直传文件二进制（仅 H5：fetch PUT；weapp 侧 Task 4
 * 再定直传方案）。注意 smoke 走 SDK put_object，前端直传是预签名 URL 的正途。
 */
export async function uploadToStorage(presigned: PresignOut, blob: Blob, contentType: string): Promise<void> {
  const res = await fetch(presigned.upload_url, {
    method: 'PUT',
    body: blob,
    headers: { 'Content-Type': contentType },
  })
  if (!res.ok) {
    let detail = `对象存储直传失败（HTTP ${res.status}）`
    try {
      const text = await res.text()
      if (text) detail += `：${text.slice(0, 200)}`
    } catch {
      /* 无响应体 */
    }
    throw { status: res.status, detail, raw: undefined }
  }
}

/** POST /media：直传完成后登记元数据入库（触发转码/校验） */
export async function registerMedia(payload: MediaRegisterIn): Promise<MediaRegisteredOut> {
  return request<MediaRegisteredOut>('/media', { method: 'POST', data: payload })
}

/** GET /media/my：我的作品列表 */
export async function myMedia(): Promise<MediaOut[]> {
  return request<MediaOut[]>('/media/my')
}

/** GET /media/{id}/url：取带签名的访问 URL */
export async function mediaUrl(mediaId: number | string): Promise<MediaUrlOut> {
  return request<MediaUrlOut>(`/media/${mediaId}/url`)
}
