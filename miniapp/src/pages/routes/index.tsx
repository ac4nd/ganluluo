/**
 * 路线库页（M7 Task 3，对齐原型 10-routes）：
 * - GET /routes（公开端点）：筛选 chips（全部 + 8 运动枚举 + 难度≤3 + 轨迹清晰）
 *   + region 关键词搜索（后端 region OR name 匹配，对齐矩阵 10 页「徽杭/临安」用例）
 * - RouteOut 卡片：名称/地区/运动/难度★/里程/爬升/用时/清晰度
 *   + 匹配度 bar 占位（P2 G-7 推荐端点缺口，标「待后端」）
 * - 点卡片 → /pages/route-detail/index?id=N
 */
import { useEffect, useMemo, useState } from 'react'
import { Input, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import { listRoutes, type RouteOut, type Sport } from '@/api/routes'
import { SPORTS } from '@/api/profile'
import type { ApiError } from '@/api/client'
import { M3Fab, M3TabBar } from '@/components/m3'
import './index.scss'

const DETAIL_PAGE = '/pages/route-detail/index'

/** 卡片缩略图按运动取渐变底色（对齐原型 route-card thumb 的山景配色） */
const SPORT_THUMB: Record<string, [string, string]> = {
  hiking: ['#41603a', '#0b140b'],
  'trail-running': ['#3a5a66', '#0a0f11'],
  climbing: ['#6a4a2a', '#0d0b06'],
  stream: ['#2e6a5a', '#081210'],
  cycling: ['#51663a', '#0c1208'],
  camping: ['#2a4a3a', '#0a120c'],
  skiing: ['#3a5a72', '#0a1014'],
  orienteering: ['#5a5a2a', '#10100a'],
}

const sportLabel = (key: string): string => SPORTS.find((s) => s.key === key)?.label ?? key
const sportEmoji = (key: string): string => SPORTS.find((s) => s.key === key)?.emoji ?? '🥾'

const fmtKm = (v: number): string => v.toFixed(1).replace(/\.0$/, '')
const fmtDuration = (v: number | null): string =>
  v === null || v === undefined ? '—' : `${fmtKm(v)}h`

/** 清晰度 tag 文案与色（对齐原型「轨迹清晰 · 高」blue / 中低 amber） */
function clarityMeta(clarity: string): { text: string; cls: string } {
  if (clarity === 'high') return { text: '轨迹清晰 · 高', cls: 'blue' }
  if (clarity === 'low') return { text: '清晰度 · 低', cls: 'amber' }
  return { text: '清晰度 · 中', cls: 'amber' }
}

/** 卡片缩略图：山景渐变 + 太阳（纯 SVG，无图片资源依赖） */
function RouteThumb({ route }: { route: RouteOut }) {
  const [c1, c2] = SPORT_THUMB[route.sport] ?? ['#41603a', '#0b140b']
  const gid = `rt-grad-${route.id}`
  // 用 id 做确定性微移，让卡片山形不完全一样
  const dx = (route.id % 3) * 6
  return (
    <svg className="rthumb" viewBox="0 0 100 112" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={c1} />
          <stop offset="1" stopColor={c2} />
        </linearGradient>
      </defs>
      <rect width="100" height="112" fill={`url(#${gid})`} />
      <circle cx={72 - dx} cy="24" r="13" fill="#f2dd7d" opacity=".9" />
      <path d={`M${-4 + dx} 70l34-26 26 18 24-18 24 12v56H${-4 + dx}z`} fill="#17311c" opacity=".85" />
      <path d={`M${-4 - dx} 90l30-18 28 14 26-16 24 10v32H${-4 - dx}z`} fill="#0c1c10" />
    </svg>
  )
}

export default function Routes() {
  const [routes, setRoutes] = useState<RouteOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // 筛选态：sport 单选（'' = 全部）；难度≤3 / 轨迹清晰为独立开关（对齐原型 chips）
  const [sport, setSport] = useState<Sport | ''>('')
  const [diffMax, setDiffMax] = useState(false)
  const [clarityOnly, setClarityOnly] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [kwDebounced, setKwDebounced] = useState('')

  // 搜索 400ms 防抖，避免每敲一个字打一次后端
  useEffect(() => {
    const t = setTimeout(() => setKwDebounced(keyword.trim()), 400)
    return () => clearTimeout(t)
  }, [keyword])

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    listRoutes({
      sport: sport || undefined,
      difficulty_max: diffMax ? 3 : undefined,
      clarity: clarityOnly ? 'high' : undefined,
      region: kwDebounced || undefined,
    })
      .then((rows) => {
        if (alive) setRoutes(rows)
      })
      .catch((err: ApiError) => {
        if (alive) setError(err?.detail || String(err))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [sport, diffMax, clarityOnly, kwDebounced])

  const resetAll = (): void => {
    setSport('')
    setDiffMax(false)
    setClarityOnly(false)
  }

  const hasFilter = sport !== '' || diffMax || clarityOnly
  const summary = useMemo(() => {
    if (loading) return '加载中…'
    if (error) return '加载失败'
    return `${routes.length} 条经过 AI 核验的成熟轨迹`
  }, [loading, error, routes.length])

  const openDetail = (id: number): void => {
    void Taro.navigateTo({ url: `${DETAIL_PAGE}?id=${id}` })
  }

  return (
    <View className="routes-page">
      <View className="routes-title">
        成熟<Text className="em">路线库</Text>
      </View>
      <View className="routes-sub">{summary}</View>

      {/* region / 路线名 关键词搜索（后端 region OR name） */}
      <View className="search-box">
        <Text className="search-ico">⌕</Text>
        <Input
          className="search-input"
          type="text"
          value={keyword}
          placeholder="搜索路线名或地区，如「徽杭」「临安」…"
          placeholderClass="search-placeholder"
          onInput={(e) => setKeyword(e.detail.value)}
        />
        {keyword ? (
          <Text className="search-clear" onClick={() => setKeyword('')}>
            ×
          </Text>
        ) : null}
      </View>

      {/* 筛选 chips：全部 + 8 运动 + 轨迹清晰 + 难度≤3（当天往返 F-5 缺参数未上） */}
      <View className="filter-row">
        <View className={`chip${!hasFilter ? ' on' : ''}`} onClick={resetAll}>
          🏅 全部
        </View>
        {SPORTS.map((s) => (
          <View
            key={s.key}
            className={`chip${sport === s.key ? ' on' : ''}`}
            onClick={() => setSport(sport === s.key ? '' : s.key)}
          >
            {s.emoji} {s.label}
          </View>
        ))}
        <View
          className={`chip${clarityOnly ? ' on' : ''}`}
          onClick={() => setClarityOnly(!clarityOnly)}
        >
          📍 轨迹清晰
        </View>
        <View className={`chip${diffMax ? ' on' : ''}`} onClick={() => setDiffMax(!diffMax)}>
          ⭐ 难度 ≤3
        </View>
      </View>

      {error ? <View className="routes-error">{error}</View> : null}

      {/* 卡片列表 */}
      {!loading && !error && routes.length === 0 ? (
        <View className="routes-empty">
          <View className="empty-ico">🗺️</View>
          <View className="empty-title">没有符合条件的路线</View>
          <View className="empty-sub">换个关键词或减少筛选条件试试</View>
        </View>
      ) : null}

      <View className="route-list">
        {routes.map((r) => {
          const cm = clarityMeta(r.clarity)
          return (
            <View key={r.id} className="route-card" onClick={() => openDetail(r.id)}>
              <RouteThumb route={r} />
              <View className="rinfo">
                <Text className="r-name">{r.name}</Text>
                <Text className="r-region">{r.region}</Text>
                <View className="rtags">
                  <View className="tag">
                    {sportEmoji(r.sport)} {sportLabel(r.sport)}
                  </View>
                  <View className="tag">★{r.difficulty}</View>
                  <View className={`tag ${cm.cls}`}>{cm.text}</View>
                </View>
                <View className="r-meta">
                  <Text>
                    <Text className="b">{fmtKm(r.distance_km)}</Text> km
                  </Text>
                  <Text>
                    ↑<Text className="b">{r.climb_m}</Text> m
                  </Text>
                  <Text>
                    ≈<Text className="b">{fmtDuration(r.duration_h)}</Text>
                  </Text>
                </View>
                {/* 匹配度 bar：P2 G-7 无推荐端点，占位标「待后端」（对齐矩阵结论） */}
                <View className="r-match">
                  <Text className="r-match-label">匹配度</Text>
                  <View className="r-match-bar">
                    <View className="r-match-fill" />
                  </View>
                  <Text className="r-match-note">待后端</Text>
                </View>
              </View>
            </View>
          )
        })}
      </View>

      {/* M8 Task 3 安卓形态：AI 对话 FAB + M3 药丸底导航（四主页面共用） */}
      <M3Fab />
      <M3TabBar active="routes" />
    </View>
  )
}
