/**
 * 路线详情页（M7 Task 3，对齐原型 08-route-detail）：
 * - GET /routes/{id}（公开）→ RouteDetailOut
 * - 指标四项（难度★/里程/爬升/用时）+ clarity chips（信号/补给/下撤点为 P2 G-10 占位「待后端」）
 * - elevation SVG 折线（零依赖手绘）+ pace SVG 折线 + terrain 比例条 + warning 安全提醒
 *   + required_gear 装备 chips（MVP 直接展示，与我的装备比对留 Task 后续）
 * - 轨迹 tab：track_points 俯视小图（lat/lon 连线）+ ele 曲线；无轨迹显示空态（F-3 已修，
 *   种子路线未上传轨迹为 null）
 * - 「加入计划」→ 半屏表单（date/time picker）→ POST /trips → toast → 跳 /pages/trips（Task 4 落地，
 *   未注册则回退 navigateBack）；收藏按钮 UI 位 → toast「收藏功能待后端」（G-13）
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'

import {
  asElevation,
  asPace,
  asTerrain,
  asTrackPoints,
  getRoute,
  trackCumKm,
  type ElevPoint,
  type RouteDetailOut,
  type TerrainSeg,
  type TrackPoint,
} from '@/api/routes'
import { createTrip } from '@/api/trips'
import { getCatalog } from '@/api/gear'
import { SPORTS } from '@/api/profile'
import { getTokenPair, LOGIN_PAGE, type ApiError } from '@/api/client'
import './index.scss'

const TRIPS_PAGE = '/pages/trips/index'

const sportMeta = (key: string): { label: string; emoji: string } => {
  const s = SPORTS.find((x) => x.key === key)
  return { label: s?.label ?? key, emoji: s?.emoji ?? '🥾' }
}

const fmtNum = (v: number): string => v.toFixed(1).replace(/\.0$/, '')

/** 装备 item_key → emoji（后端 catalog 有中文 label，emoji 是补充视觉） */
const GEAR_EMOJI: Record<string, string> = {
  boots: '🥾',
  'rain-gear': '🌧️',
  midlayer: '🧥',
  'first-aid': '⛑️',
  headlamp: '🔦',
  poles: '🥢',
  sunscreen: '🧴',
  'sun-cap': '🧢',
  backpack: '🎒',
  shell: '🧥',
}
const gearLabelOf = (key: string, catalog: Record<string, string>): string =>
  catalog[key] ?? key

/* ================= SVG 图表数据构造（零依赖，纯函数便于复算） ================= */

const CHART_W = 320

/** 通用折线投影：data 点 → viewBox 坐标（含 padding 与 8% 上下留白） */
function project(
  pts: { x: number; y: number }[],
  w: number,
  h: number,
  padL: number,
  padR: number,
  padT: number,
  padB: number,
): { px: number; py: number }[] {
  const xs = pts.map((p) => p.x)
  const ys = pts.map((p) => p.y)
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  let y0 = Math.min(...ys)
  let y1 = Math.max(...ys)
  if (x1 - x0 < 1e-9) return pts.map(() => ({ px: padL, py: padT }))
  const yPad = (y1 - y0) * 0.08 || Math.max(1, Math.abs(y1) * 0.08)
  y0 -= yPad
  y1 += yPad
  const sx = (v: number): number => padL + ((v - x0) / (x1 - x0)) * (w - padL - padR)
  const sy = (v: number): number => padT + (1 - (v - y0) / (y1 - y0)) * (h - padT - padB)
  return pts.map((p) => ({ px: +sx(p.x).toFixed(1), py: +sy(p.y).toFixed(1) }))
}

function toPolyline(coords: { px: number; py: number }[]): string {
  return coords.map((c) => `${c.px},${c.py}`).join(' ')
}

function areaPath(coords: { px: number; py: number }[], bottomY: number): string {
  if (coords.length === 0) return ''
  const head = `M${coords[0].px} ${bottomY}`
  const line = coords.map((c) => `L${c.px} ${c.py}`).join(' ')
  return `${head} ${line} L${coords[coords.length - 1].px} ${bottomY} Z`
}

/** 高程图坐标（km→x 上坡向右，m→y） */
function elevCoords(pts: ElevPoint[]): { px: number; py: number }[] {
  return project(
    pts.map((p) => ({ x: p.km, y: p.m })),
    CHART_W,
    150,
    40,
    12,
    10,
    22,
  )
}

/** 配速图坐标（pace 越大越慢 → y 越高，与原型 16′/km 在上、8′/km 在下一致） */
function paceCoords(pts: { km: number; pace: number }[]): { px: number; py: number }[] {
  return project(
    pts.map((p) => ({ x: p.km, y: p.pace })),
    CHART_W,
    130,
    44,
    12,
    12,
    22,
  )
}

/** 轨迹俯视图坐标：lat/lon → viewBox，按 cos(纬度) 修正纵横比后等比缩放置中 */
function trackMapCoords(points: TrackPoint[], w: number, h: number): { px: number; py: number }[] {
  const lats = points.map((p) => p.lat)
  const lons = points.map((p) => p.lon)
  const lat0 = Math.min(...lats)
  const lat1 = Math.max(...lats)
  const lon0 = Math.min(...lons)
  const lon1 = Math.max(...lons)
  const k = Math.cos(((lat0 + lat1) / 2) * (Math.PI / 180))
  const xs = points.map((p) => (p.lon - lon0) * k)
  const ys = points.map((p) => lat1 - p.lat)
  const spanX = Math.max(...xs) - Math.min(...xs) || 1e-6
  const spanY = Math.max(...ys) - Math.min(...ys) || 1e-6
  const pad = 14
  const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY)
  const offX = (w - spanX * scale) / 2
  const offY = (h - spanY * scale) / 2
  return points.map((_, i) => ({
    px: +(offX + (xs[i] - Math.min(...xs)) * scale).toFixed(1),
    py: +(offY + (ys[i] - Math.min(...ys)) * scale).toFixed(1),
  }))
}

/** 轨迹 ele 曲线坐标：x=累计里程 km，y=海拔 m */
function trackEleCoords(points: TrackPoint[], cumKm: number[]): { px: number; py: number }[] {
  const withEle = points
    .map((p, i) => ({ x: cumKm[i] ?? 0, y: p.ele }))
    .filter((p): p is { x: number; y: number } => p.y !== null)
  if (withEle.length < 2) return []
  return project(withEle, CHART_W, 130, 44, 12, 12, 22)
}

/* ================= 页面 ================= */

const TERRAIN_COLORS = ['#a4f150', '#62b946', '#e5c26b', '#6ec8ff', '#ffc857', '#ff6d5a']

const todayStr = (): string => {
  const d = new Date()
  const p = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export default function RouteDetail() {
  const router = useRouter()
  const routeId = Number(router.params.id)

  const [detail, setDetail] = useState<RouteDetailOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [gearLabels, setGearLabels] = useState<Record<string, string>>({})
  const [tab, setTab] = useState<'info' | 'track'>('info')

  // 加入计划半屏表单
  const [sheetOpen, setSheetOpen] = useState(false)
  const [date, setDate] = useState(todayStr())
  const [meetAt, setMeetAt] = useState('08:00')
  const [meetPlace, setMeetPlace] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitErr, setSubmitErr] = useState('')

  const load = useCallback(async (): Promise<void> => {
    if (!Number.isFinite(routeId) || routeId <= 0) {
      setError('缺少路线 id')
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const d = await getRoute(routeId)
      setDetail(d)
    } catch (err) {
      const e = err as ApiError
      setError(e?.detail || String(err))
    } finally {
      setLoading(false)
    }
  }, [routeId])

  // 详情是公开端点；装备目录也是公开端点，只用来把 item_key 翻译成中文 label，失败不阻塞
  useEffect(() => {
    void load()
    getCatalog()
      .then((cat) => {
        const map: Record<string, string> = {}
        for (const it of cat.items) map[it.key] = it.label
        setGearLabels(map)
      })
      .catch(() => {
        /* label 缺失时回退 item_key 原文 */
      })
  }, [load])

  /* ---------- 图表数据（memo：detail 不变则不重算） ---------- */
  const elevation = useMemo(() => (detail ? asElevation(detail.elevation) : []), [detail])
  const pace = useMemo(() => (detail ? asPace(detail.pace) : []), [detail])
  const terrain = useMemo(() => (detail ? asTerrain(detail.terrain) : []), [detail])
  const trackPoints = useMemo(() => (detail ? asTrackPoints(detail.track_points) : []), [detail])

  const elev = useMemo(() => (elevation.length >= 2 ? elevCoords(elevation) : []), [elevation])
  const pce = useMemo(() => (pace.length >= 2 ? paceCoords(pace) : []), [pace])
  const mapPts = useMemo(
    () => (trackPoints.length >= 2 ? trackMapCoords(trackPoints, CHART_W, 210) : []),
    [trackPoints],
  )
  const eleCurve = useMemo(
    () => (trackPoints.length >= 2 ? trackEleCoords(trackPoints, trackCumKm(trackPoints)) : []),
    [trackPoints],
  )
  const maxEle = elevation.length ? Math.max(...elevation.map((p) => p.m)) : 0
  const minEle = elevation.length ? Math.min(...elevation.map((p) => p.m)) : 0
  const maxKm = elevation.length ? elevation[elevation.length - 1].km : 0
  const trackEndKm = trackPoints.length >= 2 ? trackCumKm(trackPoints).slice(-1)[0] : 0

  /* ---------- 交互 ---------- */
  const openPlanSheet = (): void => {
    if (!getTokenPair()) {
      void Taro.showToast({ title: '请先登录', icon: 'none' })
      setTimeout(() => void Taro.reLaunch({ url: LOGIN_PAGE }), 900)
      return
    }
    setSubmitErr('')
    setDate(todayStr())
    setMeetAt('08:00')
    setSheetOpen(true)
  }

  const submitPlan = async (): Promise<void> => {
    if (submitting || !detail) return
    setSubmitting(true)
    setSubmitErr('')
    try {
      await createTrip({
        route_id: detail.id,
        date,
        meet_at: meetAt,
        meet_place: meetPlace.trim() ? meetPlace.trim() : null,
      })
      setSheetOpen(false)
      void Taro.showToast({ title: '已加入计划', icon: 'success', duration: 1500 })
      // 行程页在 Task 4 落地：未注册路由则回退详情（navigateTo 失败走 catch）
      setTimeout(() => {
        void Taro.navigateTo({ url: TRIPS_PAGE }).catch(() => {
          void Taro.navigateBack().catch(() => undefined)
        })
      }, 1500)
    } catch (err) {
      const e = err as ApiError
      setSubmitErr(e?.detail || String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const tapFavorite = (): void => {
    void Taro.showToast({ title: '收藏功能待后端', icon: 'none' })
  }

  const goBack = (): void => {
    void Taro.navigateBack().catch(() => {
      void Taro.reLaunch({ url: '/pages/index/index' })
    })
  }

  /* ---------- 加载 / 错误态 ---------- */
  if (loading) {
    return (
      <View className="rd-page">
        <View className="rd-state-card">加载中…</View>
      </View>
    )
  }
  if (error || !detail) {
    return (
      <View className="rd-page">
        <View className="rd-state-card">
          <View className="rd-state-title">加载失败</View>
          <View className="rd-state-sub">{error || '未知错误'}</View>
          <View className="btn btn-ghost rd-retry" onClick={() => void load()}>
            重试
          </View>
        </View>
      </View>
    )
  }

  const sm = sportMeta(detail.sport)
  const clarityText =
    detail.clarity === 'high' ? '高' : detail.clarity === 'low' ? '低' : '中'

  return (
    <View className="rd-page">
      {/* ---------- 封面 ---------- */}
      <View className="rd-hero">
        <svg viewBox="0 0 400 220" preserveAspectRatio="xMidYMid slice" className="rd-hero-svg">
          <defs>
            <linearGradient id="rd-sky" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#4a6a3c" />
              <stop offset=".45" stopColor="#2a452c" />
              <stop offset="1" stopColor="#0b140b" />
            </linearGradient>
          </defs>
          <rect width="400" height="220" fill="url(#rd-sky)" />
          <circle cx="88" cy="58" r="24" fill="#f2dd7d" opacity=".92" />
          <path d="M0 130l86-56 58 36 76-52 70 46 58-30 52 26v120H0z" fill="#1a3120" />
          <path d="M0 168l70-36 62 28 82-40 72 36 58-24 56 24v64H0z" fill="#0e2013" />
          <path d="M0 196l64-22 58 16 78-28 70 22 60-16 70 18v34H0z" fill="#081108" />
        </svg>
        <View className="rd-hero-shade" />
        <View className="rd-hero-btns">
          <View className="icon-btn" onClick={goBack}>
            ‹
          </View>
          <View className="icon-btn" onClick={tapFavorite}>
            ♡
          </View>
        </View>
        <View className="rd-hero-cap">
          <View className="rd-hero-tags">
            <View className="tag">
              {sm.emoji} {sm.label}
            </View>
            <View className="tag">★{detail.difficulty}</View>
            <View className="tag blue">成熟路线 · 待后端热度</View>
          </View>
          <View className="rd-hero-name">{detail.name}</View>
          <View className="rd-hero-region">
            {detail.region} · 最高海拔 {fmtNum(maxEle)} m
          </View>
        </View>
      </View>

      {/* ---------- tabs ---------- */}
      <View className="rd-tabs">
        <View className={`rd-tab${tab === 'info' ? ' on' : ''}`} onClick={() => setTab('info')}>
          概况
        </View>
        <View className={`rd-tab${tab === 'track' ? ' on' : ''}`} onClick={() => setTab('track')}>
          轨迹{trackPoints.length > 0 ? ` · ${trackPoints.length} 点` : ''}
        </View>
      </View>

      {/* ================= 概况 tab ================= */}
      {tab === 'info' ? (
        <View className="rd-body">
          {/* 指标四项 */}
          <View className="metrics">
            <View className="metric">
              <View className="v stars">
                <Text className="s-on">{'★'.repeat(Math.max(0, Math.min(5, detail.difficulty)))}</Text>
                <Text className="s-off">{'★'.repeat(Math.max(0, 5 - detail.difficulty))}</Text>
              </View>
              <View className="k">难度 / 5</View>
            </View>
            <View className="metric hl">
              <View className="v">{fmtNum(detail.distance_km)}</View>
              <View className="k">里程 km</View>
            </View>
            <View className="metric">
              <View className="v">{detail.climb_m}</View>
              <View className="k">爬升 m</View>
            </View>
            <View className="metric">
              <View className="v">
                ≈{detail.duration_h === null ? '—' : fmtNum(detail.duration_h)}h
              </View>
              <View className="k">建议用时</View>
            </View>
          </View>

          {/* info chips：真实 clarity + P2 G-10 占位（信号/补给/下撤点无字段，标注待后端） */}
          <View className="info-chips">
            <View className="chip on">📍 轨迹清晰度：{clarityText}</View>
            <View className="chip dim">📶 沿途信号 · 待后端</View>
            <View className="chip dim">🏪 补给点 · 待后端</View>
            <View className="chip dim">🚻 下撤点 · 待后端</View>
          </View>

          {/* 高程变化 */}
          <View className="chart-card">
            <View className="chart-head">
              <Text className="t">⛰️ 高程变化</Text>
              <Text className="badge-val">最高 {fmtNum(maxEle)} m</Text>
            </View>
            {elev.length >= 2 ? (
              <svg viewBox={`0 0 ${CHART_W} 150`} className="chart-svg">
                <defs>
                  <linearGradient id="rd-elev-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#a4f150" stopOpacity=".32" />
                    <stop offset="1" stopColor="#a4f150" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <g stroke="rgba(255,255,255,.08)" strokeWidth="1">
                  <line x1="40" y1="10" x2={CHART_W - 12} y2="10" />
                  <line x1="40" y1="77" x2={CHART_W - 12} y2="77" />
                  <line x1="40" y1="128" x2={CHART_W - 12} y2="128" />
                </g>
                <g fontSize="9" fill="#74825f">
                  <text x="8" y="14">{Math.round(maxEle)}m</text>
                  <text x="8" y="131">{Math.round(minEle)}m</text>
                  <text x="40" y="146">0km</text>
                  <text x={(CHART_W - 12 + 40) / 2 - 8} y="146">
                    {fmtNum(maxKm / 2)}
                  </text>
                  <text x={CHART_W - 12} y="146" textAnchor="end">
                    {fmtNum(maxKm)}km
                  </text>
                </g>
                <path d={areaPath(elev, 128)} fill="url(#rd-elev-fill)" />
                <polyline
                  points={toPolyline(elev)}
                  fill="none"
                  stroke="#a4f150"
                  strokeWidth="2.2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                <circle cx={elev[0].px} cy={elev[0].py} r="3.4" fill="#a4f150" />
                <circle
                  cx={elev[elev.length - 1].px}
                  cy={elev[elev.length - 1].py}
                  r="3.4"
                  fill="#a4f150"
                />
              </svg>
            ) : (
              <View className="chart-empty">暂无高程数据（未上传轨迹）</View>
            )}
          </View>

          {/* 建议配速 */}
          <View className="chart-card">
            <View className="chart-head">
              <Text className="t">⏱️ 建议配速</Text>
              <Text className="badge-val">通用口径 · 待后端个性化</Text>
            </View>
            {pce.length >= 2 ? (
              <svg viewBox={`0 0 ${CHART_W} 130`} className="chart-svg">
                <g stroke="rgba(255,255,255,.08)" strokeWidth="1">
                  <line x1="44" y1="12" x2={CHART_W - 12} y2="12" />
                  <line x1="44" y1="75" x2={CHART_W - 12} y2="75" />
                  <line x1="44" y1="108" x2={CHART_W - 12} y2="108" />
                </g>
                <g fontSize="9" fill="#74825f">
                  <text x="8" y="16">{fmtNum(Math.max(...pace.map((p) => p.pace)))}′/km</text>
                  <text x="8" y="111">{fmtNum(Math.min(...pace.map((p) => p.pace)))}′/km</text>
                  <text x="44" y="126">0km</text>
                  <text x={CHART_W - 12} y="126" textAnchor="end">
                    {fmtNum(pace[pace.length - 1].km)}km
                  </text>
                </g>
                <polyline
                  points={toPolyline(pce)}
                  fill="none"
                  stroke="#ffc857"
                  strokeWidth="2.2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {pce.map((c, i) => (
                  <circle key={i} cx={c.px} cy={c.py} r="3" fill="#0d1506" stroke="#ffc857" strokeWidth="1.6" />
                ))}
              </svg>
            ) : (
              <View className="chart-empty">暂无配速数据</View>
            )}
          </View>

          {/* 地形构成比例条 */}
          <View className="chart-card">
            <View className="chart-head">
              <Text className="t">🗺️ 地形构成</Text>
              <Text className="badge-val">AI 路段判读</Text>
            </View>
            {terrain.length > 0 ? (
              <>
                <View className="terr">
                  {terrain.map((seg: TerrainSeg, i) => (
                    <View
                      key={i}
                      className="terr-seg"
                      style={{
                        width: `${seg.pct}%`,
                        background: TERRAIN_COLORS[i % TERRAIN_COLORS.length],
                      }}
                    />
                  ))}
                </View>
                <View className="terr-legend">
                  {terrain.map((seg: TerrainSeg, i) => (
                    <View key={i} className="li">
                      <View
                        className="sw"
                        style={{ background: TERRAIN_COLORS[i % TERRAIN_COLORS.length] }}
                      />
                      <Text className="li-name">{seg.type}</Text>
                      <Text className="li-pct">{seg.pct}%</Text>
                    </View>
                  ))}
                </View>
              </>
            ) : (
              <View className="chart-empty">暂无地形数据</View>
            )}
          </View>

          {/* 必备装备 chips */}
          {detail.required_gear.length > 0 ? (
            <View className="chart-card">
              <View className="chart-head">
                <Text className="t">🎒 必备装备</Text>
                <Text className="badge-val">共 {detail.required_gear.length} 件</Text>
              </View>
              <View className="gear-chips">
                {detail.required_gear.map((key) => (
                  <View key={key} className="chip">
                    {GEAR_EMOJI[key] ?? '🧰'} {gearLabelOf(key, gearLabels)}
                  </View>
                ))}
              </View>
              <View className="gear-note">与「我的装备」自动比对在后续任务接入</View>
            </View>
          ) : null}

          {/* 安全提醒 */}
          {detail.warning ? (
            <View className="notice">
              <Text className="n-ico">⚠️</Text>
              <Text className="n-text">安全提醒：{detail.warning}</Text>
            </View>
          ) : null}
        </View>
      ) : null}

      {/* ================= 轨迹 tab ================= */}
      {tab === 'track' ? (
        <View className="rd-body">
          {trackPoints.length >= 2 ? (
            <>
              <View className="chart-card">
                <View className="chart-head">
                  <Text className="t">🧭 轨迹俯视图</Text>
                  <Text className="badge-val">{trackPoints.length} 点 · {fmtNum(trackEndKm)} km</Text>
                </View>
                <svg viewBox={`0 0 ${CHART_W} 210`} className="chart-svg">
                  <rect
                    x="2"
                    y="2"
                    width={CHART_W - 4}
                    height="206"
                    rx="14"
                    fill="rgba(255,255,255,.03)"
                    stroke="rgba(255,255,255,.07)"
                  />
                  <polyline
                    points={toPolyline(mapPts)}
                    fill="none"
                    stroke="#a4f150"
                    strokeWidth="2.4"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                  <circle cx={mapPts[0].px} cy={mapPts[0].py} r="5" fill="#a4f150" />
                  <circle cx={mapPts[0].px} cy={mapPts[0].py} r="2" fill="#0d1506" />
                  <circle
                    cx={mapPts[mapPts.length - 1].px}
                    cy={mapPts[mapPts.length - 1].py}
                    r="5"
                    fill="#6ec8ff"
                  />
                  <circle
                    cx={mapPts[mapPts.length - 1].px}
                    cy={mapPts[mapPts.length - 1].py}
                    r="2"
                    fill="#0d1506"
                  />
                  <text x={mapPts[0].px + 8} y={mapPts[0].py + 4} fontSize="10" fill="#a7b494">
                    起点
                  </text>
                  <text
                    x={mapPts[mapPts.length - 1].px - 8}
                    y={mapPts[mapPts.length - 1].py - 8}
                    fontSize="10"
                    fill="#a7b494"
                    textAnchor="end"
                  >
                    终点
                  </text>
                </svg>
              </View>
              <View className="chart-card">
                <View className="chart-head">
                  <Text className="t">📈 轨迹海拔</Text>
                  <Text className="badge-val">按累计里程</Text>
                </View>
                {eleCurve.length >= 2 ? (
                  <svg viewBox={`0 0 ${CHART_W} 130`} className="chart-svg">
                    <g stroke="rgba(255,255,255,.08)" strokeWidth="1">
                      <line x1="44" y1="12" x2={CHART_W - 12} y2="12" />
                      <line x1="44" y1="75" x2={CHART_W - 12} y2="75" />
                      <line x1="44" y1="108" x2={CHART_W - 12} y2="108" />
                    </g>
                    <polyline
                      points={toPolyline(eleCurve)}
                      fill="none"
                      stroke="#6ec8ff"
                      strokeWidth="2"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  </svg>
                ) : (
                  <View className="chart-empty">轨迹点缺少海拔数据</View>
                )}
              </View>
              <View className="track-note">
                3D 影像轨迹飞行依赖 track_points（F-3 已暴露），播放器在后续任务接入。
              </View>
            </>
          ) : (
            <View className="rd-state-card track-empty">
              <View className="empty-ico">🛰️</View>
              <View className="rd-state-title">未上传轨迹</View>
              <View className="rd-state-sub">该路线还没有 GPX 轨迹，上传后可查看俯视图与海拔曲线</View>
            </View>
          )}
        </View>
      ) : null}

      {/* ---------- 底部操作条 ---------- */}
      <View className="action-bar">
        <View className="sq-btn" onClick={tapFavorite}>
          ♡
        </View>
        <View className="btn btn-primary bar-main" onClick={openPlanSheet}>
          加入计划
        </View>
      </View>

      {/* ---------- 加入计划半屏表单 ---------- */}
      {sheetOpen ? (
        <View className="sheet-mask" onClick={() => setSheetOpen(false)}>
          <View className="sheet" onClick={(e) => e.stopPropagation()}>
            <View className="sheet-title">加入计划</View>
            <View className="sheet-sub">{detail.name}</View>

            <View className="sheet-field">
              <Text className="sf-label">出发日期</Text>
              <Picker mode="date" value={date} onChange={(e) => setDate(e.detail.value)}>
                <View className="sf-value">📅 {date}</View>
              </Picker>
            </View>
            <View className="sheet-field">
              <Text className="sf-label">集合时间</Text>
              <Picker mode="time" value={meetAt} onChange={(e) => setMeetAt(e.detail.value)}>
                <View className="sf-value">⏰ {meetAt}</View>
              </Picker>
            </View>
            <View className="sheet-field">
              <Text className="sf-label">集合地点（选填）</Text>
              <Input
                className="sf-input"
                type="text"
                value={meetPlace}
                placeholder="如：地铁站 A 口"
                placeholderClass="sf-placeholder"
                onInput={(e) => setMeetPlace(e.detail.value)}
              />
            </View>

            {submitErr ? <View className="sheet-err">{submitErr}</View> : null}

            <View
              className={`btn btn-primary sheet-submit${submitting ? ' is-loading' : ''}`}
              onClick={() => void submitPlan()}
            >
              {submitting ? '提交中…' : '确认加入计划'}
            </View>
          </View>
        </View>
      ) : null}
    </View>
  )
}
