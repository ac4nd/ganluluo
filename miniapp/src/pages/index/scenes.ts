/**
 * 首页场景插画（照抄 05 原型 scene SVG 的字符串化 data URI 版）。
 *
 * 为什么不是内联 <svg>：weapp 不支持 <svg> 标签与 <use href>（跨文件 CORS），
 * 而 <Image> 组件支持 SVG data URI（双端通用）。渐变色值属插画数据，非主题 token。
 * 图标内 stroke 不用 currentColor（data URI 无上下文色），写死 on-accent 深色。
 */

/** SVG inner 内容 → data URI（encodeURIComponent 处理 # 等保留字符）。 */
export function svgUri(inner: string, viewBox: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" preserveAspectRatio="xMidYMid slice">${inner}</svg>`
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

/* ---------- hero / 上半屏：hsky 渐变山景 + 太阳 + 山脊两层 + 底部光晕（400 宽） ---------- */

export function mountainSceneUri(tall = false): string {
  const h = tall ? 360 : 240
  const dy = tall ? 120 : 0
  const inner =
    `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="#41603a"/><stop offset=".52" stop-color="#26402a"/><stop offset="1" stop-color="#0b140b"/>` +
    `</linearGradient></defs>` +
    `<rect width="400" height="${h}" fill="url(#g)"/>` +
    `<circle cx="302" cy="${76 + dy}" r="30" fill="#f2dd7d" opacity=".95"/>` +
    `<circle cx="302" cy="${76 + dy}" r="55" fill="#f2dd7d" opacity=".14"/>` +
    `<path d="M0 ${150 + dy}l80-58 62 44 70-52 78 58 62-40 48 34v96H0z" fill="#17311c"/>` +
    `<path d="M0 ${188 + dy}l72-42 64 36 86-48 74 44 60-30 44 26v76H0z" fill="#0c1c10"/>` +
    `<ellipse cx="210" cy="${212 + dy}" rx="230" ry="34" fill="#a4f150" opacity=".06"/>`
  return svgUri(inner, `0 0 400 ${h}`)
}

/* ---------- mini-card 场景图（200x120，s1-s6 六款渐变模板，按 variant 取用） ---------- */

const MINI_INNER: string[] = [
  // s1 暖棕山脊 + 大阳
  `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6a4a2a"/><stop offset=".55" stop-color="#33260f"/><stop offset="1" stop-color="#0d0b06"/></linearGradient></defs>` +
    `<rect width="200" height="120" fill="url(#g)"/><circle cx="150" cy="34" r="16" fill="#ffc857" opacity=".9"/>` +
    `<path d="M0 78l50-30 40 22 45-34 40 30 25-14v68H0z" fill="#1d1a0e"/><path d="M0 96l45-24 40 18 50-26 40 20 25-10v46H0z" fill="#0e0c05"/>`,
  // s2 竹海（绿条 + 双层山脊）
  `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7fb069"/><stop offset=".55" stop-color="#3a5a2c"/><stop offset="1" stop-color="#0d1a0c"/></linearGradient></defs>` +
    `<rect width="200" height="120" fill="url(#g)"/><g stroke="#0f2010" stroke-width="5" opacity=".7"><path d="M30 0v120M78 0v110M126 0v120M170 0v100"/></g>` +
    `<path d="M0 88l40-20 46 18 52-26 38 18 24-8v50H0z" fill="#0b160a"/>`,
  // s3 冷蓝山径 + 白月
  `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a5a66"/><stop offset=".55" stop-color="#22343a"/><stop offset="1" stop-color="#0a0f11"/></linearGradient></defs>` +
    `<rect width="200" height="120" fill="url(#g)"/><circle cx="60" cy="30" r="13" fill="#cfe8ff" opacity=".8"/>` +
    `<path d="M0 72l55-40 45 34 50-44 30 26 20-12v84H0z" fill="#16262c"/><path d="M0 98l50-28 44 22 56-30 30 16 20-8v50H0z" fill="#0a1114"/>`,
  // s4 青山岩壁 + 底部 accent 光晕
  `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2e6a5a"/><stop offset=".55" stop-color="#1a3a30"/><stop offset="1" stop-color="#081210"/></linearGradient></defs>` +
    `<rect width="200" height="120" fill="url(#g)"/><path d="M0 70l60-46 50 40 40-28 50 38v46H0z" fill="#123026"/>` +
    `<ellipse cx="100" cy="92" rx="120" ry="26" fill="#a4f150" opacity=".07"/><path d="M0 100l60-22 55 18 45-18 40 12v30H0z" fill="#08120e"/>`,
  // s5 黄绿晨景 + 黄日（足迹 1）
  `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4a5a2c"/><stop offset=".55" stop-color="#2a3a18"/><stop offset="1" stop-color="#0c1206"/></linearGradient></defs>` +
    `<rect width="200" height="120" fill="url(#g)"/><circle cx="46" cy="34" r="15" fill="#f2dd7d" opacity=".85"/>` +
    `<path d="M0 76l55-34 48 26 42-30 35 22 20-8v64H0z" fill="#1c2a10"/><path d="M0 96l50-22 45 16 50-22 35 14 20-6v44H0z" fill="#0b1005"/>`,
  // s6 蓝绿暮色 + 白月（足迹 2）
  `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2e5a66"/><stop offset=".55" stop-color="#1a3a44"/><stop offset="1" stop-color="#081114"/></linearGradient></defs>` +
    `<rect width="200" height="120" fill="url(#g)"/><circle cx="150" cy="30" r="12" fill="#cfe8ff" opacity=".7"/>` +
    `<path d="M0 80l46-28 44 20 56-36 34 22 20-8v70H0z" fill="#12262e"/><path d="M0 100l52-20 46 14 48-20 34 12 20-4v38H0z" fill="#08111a"/>`,
]

export function miniSceneUri(variant: number): string {
  return svgUri(MINI_INNER[variant % MINI_INNER.length], '0 0 200 120')
}

/* ---------- 运动图标（24x24，照抄 sprite symbol inner；stroke 写死深色） ---------- */

const ICON_STROKE = 'fill="none" stroke="#0d1506" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'

const SPORT_INNER: Record<string, string> = {
  hiking: `<g ${ICON_STROKE}><circle cx="13" cy="4.2" r="1.7"/><rect x="9" y="7.4" width="3.2" height="6" rx="1.5"/><path d="M12.6 7.4v5.8"/><path d="M12.5 8.6l2.6 2 .6 1.3"/><path d="M14.8 11.8h2"/><path d="M15.8 11.8V20"/><path d="M12.6 13.2l2.1 3.3 1 3.5"/><path d="M12.6 13.2l-2 3.5-.5 3.3"/></g>`,
  climbing: `<g ${ICON_STROKE}><circle cx="12" cy="3.6" r="1.7"/><path d="M6.5 2.5V21.5"/><circle cx="6.5" cy="5" r=".9"/><circle cx="6.5" cy="10" r=".9"/><circle cx="6.5" cy="15.4" r=".9"/><circle cx="6.5" cy="19.4" r=".9"/><path d="M7.5 5.1l2.6 1.4"/><path d="M11.9 5.4c.4 2.2.5 4.5.2 6.9"/><path d="M11.6 8.4 7.5 9.9"/><path d="M12 12.4l1.5 2.6-6 .5"/><path d="M12 12.4l-.6 3.9-4.2 2.8"/></g>`,
  stream: `<g ${ICON_STROKE}><circle cx="10.2" cy="5" r="1.7"/><path d="M10.9 7.2c1.1 2.3 1.9 4.6 2.3 7.1"/><path d="M11 7.8l3.5 2 2.7 4.4"/><path d="M10.7 7.5 8 8.8l-.8 3"/><path d="M18.6 11.2l1.3-1.3"/><path d="M3 16.8c2-1.6 3.6-1.6 5.5 0s3.5 1.6 5.5 0 3.5-1.6 5.5 0"/><path d="M3 20.4c2-1.6 3.6-1.6 5.5 0s3.5-1.6 5.5 0 3.5-1.6 5.5 0"/></g>`,
  'trail-running': `<g ${ICON_STROKE}><circle cx="13.9" cy="3.5" r="1.6"/><path d="M13.3 5.7c-1 1.5-1.7 3.1-2.1 4.7"/><path d="M13.4 6.2l2.7.9 1.5 2.3"/><path d="M13 6.7l-2.5 1.3-1.6 1.9"/><path d="M11.2 10.4l3.4 2 2.2 2.5"/><path d="M11.2 10.4l-2.4 1.6-2.4-2.4"/><path d="M2.5 8.5 21.5 17"/></g>`,
  cycling: `<g ${ICON_STROKE}><circle cx="5.5" cy="17.2" r="3.1"/><circle cx="18.5" cy="17.2" r="3.1"/><circle cx="12.5" cy="17.2" r="1"/><path d="M5.5 17.2 9.1 11.1l3.4 6.1"/><path d="M8.1 11.1h2"/><path d="M12.5 17.2 15.3 10.2l3.2 7"/><path d="M14.3 9.3h2.4"/><circle cx="15.6" cy="4" r="1.6"/><path d="M15.2 6c-2.1 1.4-4 2.9-5.6 4.6"/><path d="M15.1 6.2l1.3 1.7.2 1.6"/><path d="M9.7 10.7l3 2.2v4.3"/><path d="M9.7 10.7l1 3.9 2.6 1"/></g>`,
  camping: `<g ${ICON_STROKE}><path d="M3.5 20h17"/><path d="M12 4.5 2.5 20h19L12 4.5z"/><path d="M12 10.5 7.8 20h8.4L12 10.5z"/></g>`,
  skiing: `<g ${ICON_STROKE}><circle cx="14.5" cy="4.2" r="1.5"/><path d="M13.6 6.4 11 10.2l2.7 1.8 2-2.3 2.3 2.5"/><path d="M11 10.2 8.7 14.2l1.8 2"/><path d="M13.7 12 16 14.6 15 18"/><path d="M8.2 18.5 7.5 20"/><path d="M5 20.5 19 16"/><path d="M6.5 22 20 17.5"/></g>`,
  orienteering: `<g ${ICON_STROKE}><circle cx="12" cy="12" r="8.2"/><path d="M12 5.2v1.9M12 16.9v1.9M5.2 12h1.9M16.9 12h1.9"/><path d="M15.3 8.7 12.6 12.6 8.7 15.3 11.4 11.4z"/><circle cx="12" cy="12" r="1"/></g>`,
}

/** 运动图标 data URI（未知 key 兜底 hiking）。 */
export function sportIconUri(sport: string): string {
  return svgUri(SPORT_INNER[sport] ?? SPORT_INNER.hiking, '0 0 24 24')
}
