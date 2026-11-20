/**
 * 路线库页（M7 Task 3，对齐原型 10-routes；M8.6 筛选对齐「两步路」）：
 * - GET /routes（公开端点）：四行筛选 chips——运动（全部 + 8 枚举 + 难度≤3 + 轨迹清晰）
 *   / 地区（从已加载数据聚合 region 前缀）/ 时间（近一周~近三月）/ 排序（最新/标记最多）
 *   + region 关键词搜索（后端 region OR name 匹配，对齐矩阵 10 页「徽杭/临安」用例）
 * - RouteOut 卡片：封面（M8.7 /static/covers/{id}.png 轨迹示意图，失败回退渐变模板）
 *   + 名称/地区/运动/难度★/里程/爬升/用时/清晰度
 *   + 匹配度 bar 占位（P2 G-7 推荐端点缺口，标「待后端」）
 * - 点卡片 → /pages/route-detail/index?id=N
 */
import { useEffect, useMemo, useState } from 'react'
import { Image, Input, Text, View } from '@tarojs/components'
import Taro, { useReachBottom } from '@tarojs/taro'

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

/** M8.6 时间筛选档：N=0 表示全部；N 天 → created_after ISO 日期（UTC 口径，
 * 与后端 SQLite CURRENT_TIMESTAMP 的 UTC 存储对齐） */
const TIME_OPTS: { label: string; days: number }[] = [
  { label: '全部', days: 0 },
  { label: '近一周', days: 7 },
  { label: '近一月', days: 30 },
  { label: '近三月', days: 90 },
]

/** M8.6 排序档：'' = 后端缺省 id 升序 */
const SORT_OPTS: { label: string; value: '' | 'new' | 'points' }[] = [
  { label: '默认', value: '' },
  { label: '最新', value: 'new' },
  { label: '标记最多', value: 'points' },
]

const isoDaysAgo = (n: number): string =>
  new Date(Date.now() - n * 86400000).toISOString().slice(0, 10)

const fmtKm = (v: number): string => v.toFixed(1).replace(/\.0$/, '')
const fmtDuration = (v: number | null): string =>
  v === null || v === undefined ? '—' : `${fmtKm(v)}h`

/** 清晰度 tag 文案与色（对齐原型「轨迹清晰 · 高」blue / 中低 amber） */
function clarityMeta(clarity: string): { text: string; cls: string } {
  if (clarity === 'high') return { text: '轨迹清晰 · 高', cls: 'blue' }
  if (clarity === 'low') return { text: '清晰度 · 低', cls: 'amber' }
  return { text: '清晰度 · 中', cls: 'amber' }
}

/** 卡片缩略图：真实封面（RouteOut.cover_url，M8.8 MinIO）叠在山景渐变兜底上；
 * cover_url 空 或 加载失败（covered=false）回退渐变 */
function RouteThumb({ route, covered, onFail }: {
  route: RouteOut
  covered: boolean
  onFail: (id: number) => void
}) {
  const [c1, c2] = SPORT_THUMB[route.sport] ?? ['#41603a', '#0b140b']
  const gid = `rt-grad-${route.id}`
  // 用 id 做确定性微移，让卡片山形不完全一样
  const dx = (route.id % 3) * 6
  return (
    <View className="rthumb-box">
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
      {covered && route.cover_url ? (
        <Image
          className="rthumb-img"
          mode="aspectFill"
          lazyLoad
          src={route.cover_url}
          onError={() => onFail(route.id)}
        />
      ) : null}
    </View>
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
  // M8.6：地区（'' = 全部，选中词作 region 参数）/ 时间（0 = 全部）/ 排序（'' = 默认）
  const [regionSel, setRegionSel] = useState('')
  const [days, setDays] = useState(0)
  const [sort, setSort] = useState<'' | 'new' | 'points'>('')
  // 地区 chips 词表：从已加载 routes 聚合 region 前缀（省/市两字口径），
  // 跨筛选累积——选中某地区后列表收窄，其余地区词仍可选
  const [regionSeen, setRegionSeen] = useState<string[]>([])
  // M8.7 封面加载失败标记（页面级 Set）：失败 id 回退渐变模板（函数式 add 防重复触发）
  const [failedCovers, setFailedCovers] = useState<Set<number>>(new Set())
  const markCoverFail = (id: number): void => {
    setFailedCovers((prev) => (prev.has(id) ? prev : new Set(prev).add(id)))
  }

  /* 分页（M8.7 I-1：1141 条不全量拉）：page 从 0 起，筛选变更重置回 0（替换列表），
     触底 page+1（追加）；返回不足一页即到底。 */
  const PAGE = 20
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(false)

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
      region: kwDebounced || regionSel || undefined,
      created_after: days ? isoDaysAgo(days) : undefined,
      sort: sort || undefined,
      limit: PAGE,
      offset: page * PAGE,
    })
      .then((rows) => {
        if (!alive) return
        setRoutes((prev) => (page === 0 ? rows : [...prev, ...rows]))
        setHasMore(rows.length >= PAGE)
        // 地区词表取第一页样本即可（跨筛选累积，全量无必要）
        if (page === 0) {
          const words = rows.map((r) => r.region.slice(0, 2))
          if (words.length) setRegionSeen((prev) => Array.from(new Set([...prev, ...words])))
        }
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
  }, [sport, diffMax, clarityOnly, kwDebounced, regionSel, days, sort, page])

  /** 触底加载下一页（Taro 页面级滚动钩子，H5/weapp 双端支持） */
  useReachBottom(() => {
    if (hasMore && !loading) setPage((p) => p + 1)
  })

  /** 筛选变更重置回第一页（各 setter 包装：先 setPage(0) 再改值） */
  const resetAll = (): void => {
    setPage(0)
    setSport('')
    setDiffMax(false)
    setClarityOnly(false)
    setRegionSel('')
    setDays(0)
    setSort('')
  }

  const hasFilter =
    sport !== '' || diffMax || clarityOnly || regionSel !== '' || days !== 0 || sort !== ''

  /** 选地区词：清掉关键词搜索（两者共用后端 region 参数，互斥避免语义打架） */
  const pickRegion = (word: string): void => {
    setPage(0)
    setRegionSel(word)
    setKeyword('')
    setKwDebounced('')
  }
  const summary = useMemo(() => {
    // 分页追加（page>0）不闪"加载中"，已加载条数实时可见
    if (loading && page === 0) return '加载中…'
    if (error) return '加载失败'
    return `已加载 ${routes.length} 条${hasMore ? '，上滑加载更多' : ''}`
  }, [loading, page, error, routes.length, hasMore])

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
          onInput={(e) => {
            const v = e.detail.value
            setPage(0)
            setKeyword(v)
            if (v.trim()) setRegionSel('') // 关键词与地区 chips 共用 region 参数，互斥
          }}
        />
        {keyword ? (
          <Text
            className="search-clear"
            onClick={() => {
              setPage(0)
              setKeyword('')
            }}
          >
            ×
          </Text>
        ) : null}
      </View>

      {/* 筛选区（M8.6 两步路式四行 chips，行内横向滚动；类名 frow-tag 已 grep 全项目确认无同名） */}
      <View className="filter-row">
        <View className={`chip${!hasFilter ? ' on' : ''}`} onClick={resetAll}>
          🏅 全部
        </View>
        {SPORTS.map((s) => (
          <View
            key={s.key}
            className={`chip${sport === s.key ? ' on' : ''}`}
            onClick={() => {
              setPage(0)
              setSport(sport === s.key ? '' : s.key)
            }}
          >
            {s.emoji} {s.label}
          </View>
        ))}
        <View
          className={`chip${clarityOnly ? ' on' : ''}`}
          onClick={() => {
            setPage(0)
            setClarityOnly(!clarityOnly)
          }}
        >
          📍 轨迹清晰
        </View>
        <View
          className={`chip${diffMax ? ' on' : ''}`}
          onClick={() => {
            setPage(0)
            setDiffMax(!diffMax)
          }}
        >
          ⭐ 难度 ≤3
        </View>
      </View>
      <View className="filter-row">
        <View className="frow-tag">地区</View>
        <View className={`chip${regionSel === '' ? ' on' : ''}`} onClick={() => pickRegion('')}>
          全部
        </View>
        {regionSeen.map((w) => (
          <View key={w} className={`chip${regionSel === w ? ' on' : ''}`} onClick={() => pickRegion(w)}>
            {w}
          </View>
        ))}
      </View>
      <View className="filter-row">
        <View className="frow-tag">时间</View>
        {TIME_OPTS.map((o) => (
          <View
            key={o.label}
            className={`chip${days === o.days ? ' on' : ''}`}
            onClick={() => {
              setPage(0)
              setDays(o.days)
            }}
          >
            {o.label}
          </View>
        ))}
      </View>
      <View className="filter-row">
        <View className="frow-tag">排序</View>
        {SORT_OPTS.map((o) => (
          <View
            key={o.label}
            className={`chip${sort === o.value ? ' on' : ''}`}
            onClick={() => {
              setPage(0)
              setSort(o.value)
            }}
          >
            {o.label}
          </View>
        ))}
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
              <RouteThumb route={r} covered={!failedCovers.has(r.id)} onFail={markCoverFail} />
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

      {/* 分页加载态（M8.7 I-1 触底加载）：首屏 20 条，滚动到底自动续拉 */}
      {routes.length > 0 && !error ? (
        <View className="list-foot">
          {hasMore ? '加载中…（上滑加载更多）' : `已全部加载 ${routes.length} 条`}
        </View>
      ) : null}

      {/* M8 Task 3 安卓形态：AI 对话 FAB + M3 药丸底导航（四主页面共用） */}
      <M3Fab />
      <M3TabBar active="routes" />
    </View>
  )
}
