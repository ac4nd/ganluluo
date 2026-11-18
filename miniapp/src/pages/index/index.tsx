/**
 * 首页（M75H 重做：一比一转换 protype/05-home.html 的界面结构）：
 * - ① 上半屏场景层：05 原型是视频轮播 canvas（cinema.js），miniapp MVP 用静态渐变
 *   场景 SVG（照抄 hero-card 的 hsky 渐变山景）+ cinema-shade 同款暗化盖层；
 *   视频轮播 defer（G-12 资源下发票）。absolute 定位 + 内容 relative z 上移，
 *   同构原型「content 叠加于 cinema-layer」。
 * - ② page-head：头像圆（昵称首字 / 未登录「客」灰底）+ 问候两行 + 铃铛 icon-btn
 *   （toast 占位）。登录入口并入头像点击：已登录 → profile；未登录 →
 *   wechat-login（weapp）/ login（H5），按 TARO_ENV（guard.loginEntryUrl）。
 * - ③ title-xl 两行主标题（em accent 斜体）；④ search 条 → 路线库。
 * - ⑤「AI 为你挑选」hero-card：GET /routes 取第一条渲染 name/distance_km（真实）；
 *   天气与匹配度沿用原型文案（mock，P2 G-7/G-9 待后端），卡片右上角「示例」小标标注。
 * - ⑥「附近热门路线」横滚 mini-card（scene SVG 按 s1-s4 渐变模板轮换 + m-sport
 *   运动标签）。运动图标 `<use href="#icon-*">` 引用页顶内嵌 symbol sprite
 *   （weapp `<use>` 跨文件 CORS 已知坑 → sprite 内嵌进本页，照抄原型 8 个运动 symbol）。
 * - ⑦「最近足迹」横滚：GET /trips?status=done（真实接口）渲染已完成计划；
 *   未登录 / 无足迹 → 空态文案（卡片空态）。
 * - ⑧ M3Fab + M3TabBar + 隐私弹窗：M8 语义原样保留（页面级 FAB 是 M8 安卓决策；
 *   05 原型的 hero-card 内箭头钮以 hero-fab 呈现）。
 * - NAV_ITEMS 导航列表已删除（入口页形态退役；装备入口在 profile 页保留）。
 * - M8 Task 4 游客模式不变：受限入口（全部足迹/行程 tab/我的/FAB）统一
 *   requireAuth() 弹「登录后可用」；路线库与详情公开浏览放行。
 */
import { useCallback, useState } from 'react'
import { ScrollView, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { me, getTokenPair, type UserOut } from '@/api/auth'
import { type ApiError, type TokenPair } from '@/api/client'
import { goLoginEntry, requireAuth } from '@/api/guard'
import { listRoutes, type RouteOut } from '@/api/routes'
import { listTrips, type TripPlanCard } from '@/api/trips'
import { SPORTS } from '@/api/profile'
import { agreePrivacy, startLaunchSequence } from '@/launch'
import { M3Fab, M3TabBar } from '@/components/m3'
import './index.scss'

const ROUTES_PAGE = '/pages/routes/index'
const DETAIL_PAGE = '/pages/route-detail/index'
const PROFILE_PAGE = '/pages/profile/index'

/** 运动枚举 → 页顶 sprite 的 symbol id（照抄 05 原型 8 个运动 icon） */
const SPORT_ICON: Record<string, string> = {
  hiking: 'icon-hiking',
  'trail-running': 'icon-trail-running',
  climbing: 'icon-climbing',
  stream: 'icon-stream',
  cycling: 'icon-cycling',
  camping: 'icon-camping',
  skiing: 'icon-skiing',
  orienteering: 'icon-orienteering',
}

const sportLabel = (key: string): string => SPORTS.find((s) => s.key === key)?.label ?? key

/** 26.7 → "26.7"；10 → "10"（对齐 routes 页 fmtKm 口径） */
const fmtKm = (v: number): string => v.toFixed(1).replace(/\.0$/, '')

/** "2026-11-16" → "11/16"（05 原型足迹卡 m-meta 首位格式）；解析失败回退原文 */
const mmdd = (date: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  return m ? `${m[2]}/${m[3]}` : date
}

/** 时段问候（05 原型次行「早上好 · 今日宜出行」） */
const greetByHour = (): string => {
  const h = new Date().getHours()
  if (h < 11) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
}

/**
 * 运动图标 sprite（照抄 05-home.html 页顶 8 个 symbol，逐字节同款）。
 * weapp 的 `<use>` 引用外部 svg 文件有跨文件 CORS 坑 → sprite 内嵌进本页顶部。
 */
function SportSprite(): JSX.Element {
  return (
    <svg className="sport-sprite" aria-hidden="true">
      {/* 徒步 Hiking：背包 + 登山杖 */}
      <symbol id="icon-hiking" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="13" cy="4.2" r="1.7" />
          <rect x="9" y="7.4" width="3.2" height="6" rx="1.5" />
          <path d="M12.6 7.4v5.8" />
          <path d="M12.5 8.6l2.6 2 .6 1.3" />
          <path d="M14.8 11.8h2" />
          <path d="M15.8 11.8V20" />
          <path d="M12.6 13.2l2.1 3.3 1 3.5" />
          <path d="M12.6 13.2l-2 3.5-.5 3.3" />
        </g>
      </symbol>
      {/* 攀岩 Climbing：🧗 攀爬姿态（岩壁 + 岩点 + 攀爬者） */}
      <symbol id="icon-climbing" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="3.6" r="1.7" />
          <path d="M6.5 2.5V21.5" />
          <circle cx="6.5" cy="5" r=".9" />
          <circle cx="6.5" cy="10" r=".9" />
          <circle cx="6.5" cy="15.4" r=".9" />
          <circle cx="6.5" cy="19.4" r=".9" />
          <path d="M7.5 5.1l2.6 1.4" />
          <path d="M11.9 5.4c.4 2.2.5 4.5.2 6.9" />
          <path d="M11.6 8.4 7.5 9.9" />
          <path d="M12 12.4l1.5 2.6-6 .5" />
          <path d="M12 12.4l-.6 3.9-4.2 2.8" />
        </g>
      </symbol>
      {/* 溯溪 Stream Trekking：溪流涉水/游泳姿态（上身出水 + 划水臂 + 水花 + 波浪） */}
      <symbol id="icon-stream" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="10.2" cy="5" r="1.7" />
          <path d="M10.9 7.2c1.1 2.3 1.9 4.6 2.3 7.1" />
          <path d="M11 7.8l3.5 2 2.7 4.4" />
          <path d="M10.7 7.5 8 8.8l-.8 3" />
          <path d="M18.6 11.2l1.3-1.3" />
          <path d="M3 16.8c2-1.6 3.6-1.6 5.5 0s3.5 1.6 5.5 0 3.5-1.6 5.5 0" />
          <path d="M3 20.4c2-1.6 3.6-1.6 5.5 0s3.5 1.6 5.5 0 3.5-1.6 5.5 0" />
        </g>
      </symbol>
      {/* 越野跑 Trail Running：小径下坡奔跑（下坡径线 + 前倾加速姿态） */}
      <symbol id="icon-trail-running" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="13.9" cy="3.5" r="1.6" />
          <path d="M13.3 5.7c-1 1.5-1.7 3.1-2.1 4.7" />
          <path d="M13.4 6.2l2.7.9 1.5 2.3" />
          <path d="M13 6.7l-2.5 1.3-1.6 1.9" />
          <path d="M11.2 10.4l3.4 2 2.2 2.5" />
          <path d="M11.2 10.4l-2.4 1.6-2.4-2.4" />
          <path d="M2.5 8.5 21.5 17" />
        </g>
      </symbol>
      {/* 骑行 Cycling：单车骑行姿势（整车 + 俯身骑手 + 双脚踏板） */}
      <symbol id="icon-cycling" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="5.5" cy="17.2" r="3.1" />
          <circle cx="18.5" cy="17.2" r="3.1" />
          <circle cx="12.5" cy="17.2" r="1" />
          <path d="M5.5 17.2 9.1 11.1l3.4 6.1" />
          <path d="M8.1 11.1h2" />
          <path d="M12.5 17.2 15.3 10.2l3.2 7" />
          <path d="M14.3 9.3h2.4" />
          <circle cx="15.6" cy="4" r="1.6" />
          <path d="M15.2 6c-2.1 1.4-4 2.9-5.6 4.6" />
          <path d="M15.1 6.2l1.3 1.7.2 1.6" />
          <path d="M9.7 10.7l3 2.2v4.3" />
          <path d="M9.7 10.7l1 3.9 2.6 1" />
        </g>
      </symbol>
      {/* 露营 Camping：帐篷（大 A 帐 + 内帐门） */}
      <symbol id="icon-camping" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3.5 20h17" />
          <path d="M12 4.5 2.5 20h19L12 4.5z" />
          <path d="M12 10.5 7.8 20h8.4L12 10.5z" />
        </g>
      </symbol>
      {/* 滑雪 Skiing */}
      <symbol id="icon-skiing" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="14.5" cy="4.2" r="1.5" />
          <path d="M13.6 6.4 11 10.2l2.7 1.8 2-2.3 2.3 2.5" />
          <path d="M11 10.2 8.7 14.2l1.8 2" />
          <path d="M13.7 12 16 14.6 15 18" />
          <path d="M8.2 18.5 7.5 20" />
          <path d="M5 20.5 19 16" />
          <path d="M6.5 22 20 17.5" />
        </g>
      </symbol>
      {/* 定向越野 Orienteering：指南针（表盘刻度 + 磁针） */}
      <symbol id="icon-orienteering" viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="8.2" />
          <path d="M12 5.2v1.9M12 16.9v1.9M5.2 12h1.9M16.9 12h1.9" />
          <path d="M15.3 8.7 12.6 12.6 8.7 15.3 11.4 11.4z" />
          <circle cx="12" cy="12" r="1" />
        </g>
      </symbol>
    </svg>
  )
}

/* ---------- 场景插画（照抄 05 原型 scene SVG；渐变色值属插画数据，非主题 token） ---------- */

/**
 * hero-card / 上半屏场景层同款：hsky 渐变山景 + 太阳 + 山脊两层 + 底部光晕（400x240）。
 * tall = 上半屏场景层用：viewBox 拉高到 400x360（同款渐变/山形整体下移，多出纯天空，
 * 避免 42vh 容器 slice 时太阳被放大到失真）。
 */
function MountainScene({ gid, tall = false }: { gid: string; tall?: boolean }): JSX.Element {
  const vb = tall ? '0 0 400 360' : '0 0 400 240'
  const dy = tall ? 120 : 0
  return (
    <svg className="scene" viewBox={vb} preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#41603a" />
          <stop offset=".52" stopColor="#26402a" />
          <stop offset="1" stopColor="#0b140b" />
        </linearGradient>
      </defs>
      <rect width="400" height={tall ? 360 : 240} fill={`url(#${gid})`} />
      <circle cx="302" cy={76 + dy} r="30" fill="#f2dd7d" opacity=".95" />
      <circle cx="302" cy={76 + dy} r="55" fill="#f2dd7d" opacity=".14" />
      <path d={`M0 ${150 + dy}l80-58 62 44 70-52 78 58 62-40 48 34v96H0z`} fill="#17311c" />
      <path d={`M0 ${188 + dy}l72-42 64 36 86-48 74 44 60-30 44 26v76H0z`} fill="#0c1c10" />
      <ellipse cx="210" cy={212 + dy} rx="230" ry="34" fill="#a4f150" opacity=".06" />
    </svg>
  )
}

/**
 * mini-card 场景图（200x120）：照抄 05 原型 s1-s6 六款渐变模板，按 variant 轮换——
 * 附近热门路线用 s1-s4（variant 0-3），最近足迹用 s5-s6（variant 4-5）。
 * gid 加 uid 后缀防同文档 gradient id 冲突。
 */
function MiniScene({ variant, uid }: { variant: number; uid: string }): JSX.Element {
  const gid = `s${variant + 1}-${uid}`
  if (variant === 0) {
    return (
      <svg className="scene" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#6a4a2a" />
            <stop offset=".55" stopColor="#33260f" />
            <stop offset="1" stopColor="#0d0b06" />
          </linearGradient>
        </defs>
        <rect width="200" height="120" fill={`url(#${gid})`} />
        <circle cx="150" cy="34" r="16" fill="#ffc857" opacity=".9" />
        <path d="M0 78l50-30 40 22 45-34 40 30 25-14v68H0z" fill="#1d1a0e" />
        <path d="M0 96l45-24 40 18 50-26 40 20 25-10v46H0z" fill="#0e0c05" />
      </svg>
    )
  }
  if (variant === 1) {
    return (
      <svg className="scene" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#7fb069" />
            <stop offset=".55" stopColor="#3a5a2c" />
            <stop offset="1" stopColor="#0d1a0c" />
          </linearGradient>
        </defs>
        <rect width="200" height="120" fill={`url(#${gid})`} />
        <g stroke="#0f2010" strokeWidth="5" opacity=".7">
          <path d="M30 0v120M78 0v110M126 0v120M170 0v100" />
        </g>
        <path d="M0 88l40-20 46 18 52-26 38 18 24-8v50H0z" fill="#0b160a" />
      </svg>
    )
  }
  if (variant === 2) {
    return (
      <svg className="scene" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3a5a66" />
            <stop offset=".55" stopColor="#22343a" />
            <stop offset="1" stopColor="#0a0f11" />
          </linearGradient>
        </defs>
        <rect width="200" height="120" fill={`url(#${gid})`} />
        <circle cx="60" cy="30" r="13" fill="#cfe8ff" opacity=".8" />
        <path d="M0 72l55-40 45 34 50-44 30 26 20-12v84H0z" fill="#16262c" />
        <path d="M0 98l50-28 44 22 56-30 30 16 20-8v50H0z" fill="#0a1114" />
      </svg>
    )
  }
  if (variant === 4) {
    return (
      <svg className="scene" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#4a5a2c" />
            <stop offset=".55" stopColor="#2a3a18" />
            <stop offset="1" stopColor="#0c1206" />
          </linearGradient>
        </defs>
        <rect width="200" height="120" fill={`url(#${gid})`} />
        <circle cx="46" cy="34" r="15" fill="#f2dd7d" opacity=".85" />
        <path d="M0 76l55-34 48 26 42-30 35 22 20-8v64H0z" fill="#1c2a10" />
        <path d="M0 96l50-22 45 16 50-22 35 14 20-6v44H0z" fill="#0b1005" />
      </svg>
    )
  }
  if (variant === 5) {
    return (
      <svg className="scene" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2e5a66" />
            <stop offset=".55" stopColor="#1a3a44" />
            <stop offset="1" stopColor="#081114" />
          </linearGradient>
        </defs>
        <rect width="200" height="120" fill={`url(#${gid})`} />
        <circle cx="150" cy="30" r="12" fill="#cfe8ff" opacity=".7" />
        <path d="M0 80l46-28 44 20 56-36 34 22 20-8v70H0z" fill="#12262e" />
        <path d="M0 100l52-20 46 14 48-20 34 12 20-4v38H0z" fill="#08111a" />
      </svg>
    )
  }
  // variant 3（s4）：青山岩壁 + 底部 accent 光晕
  return (
    <svg className="scene" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2e6a5a" />
          <stop offset=".55" stopColor="#1a3a30" />
          <stop offset="1" stopColor="#081210" />
        </linearGradient>
      </defs>
      <rect width="200" height="120" fill={`url(#${gid})`} />
      <path d="M0 70l60-46 50 40 40-28 50 38v46H0z" fill="#123026" />
      <ellipse cx="100" cy="92" rx="120" ry="26" fill="#a4f150" opacity=".07" />
      <path d="M0 100l60-22 55 18 45-18 40 12v30H0z" fill="#08120e" />
    </svg>
  )
}

export default function Index() {
  const [pair, setPair] = useState<TokenPair | null>(null)
  const [user, setUser] = useState<UserOut | null>(null)
  const [routes, setRoutes] = useState<RouteOut[]>([])
  const [routesErr, setRoutesErr] = useState('')
  /** 已完成行程（status=done）；null = 游客未拉取 → 足迹空态「登录后查看足迹」 */
  const [doneTrips, setDoneTrips] = useState<TripPlanCard[] | null>(null)
  // 启动序列①：首次启动（gl_privacy_ok 无值）弹半屏隐私弹窗
  const [privacyOpen, setPrivacyOpen] = useState(false)

  const refresh = useCallback(async (): Promise<void> => {
    const cur = getTokenPair()
    setPair(cur)
    // GET /routes：公开端点，游客也拉（AI 挑选 / 附近热门 双端可见）
    try {
      setRoutes(await listRoutes())
      setRoutesErr('')
    } catch (err) {
      const e = err as ApiError
      setRoutesErr(e?.detail || '路线加载失败')
      console.warn('[index] GET /routes 失败:', e?.detail)
    }
    if (!cur) {
      setUser(null)
      setDoneTrips(null)
      return
    }
    try {
      setUser(await me())
    } catch (err) {
      const e = err as ApiError
      console.warn('[index] /auth/me 失败:', e?.detail)
    }
    // M8 前置已加 status 过滤：GET /trips?status=done（真实足迹数据）
    try {
      setDoneTrips(await listTrips({ status: 'done' }))
    } catch (err) {
      const e = err as ApiError
      setDoneTrips([])
      console.warn('[index] GET /trips?status=done 失败:', e?.detail)
    }
  }, [])

  useDidShow(() => {
    void refresh()
    // 启动序列编排（launch.ts）：一次冷启动只跑一遍；未同意隐私 → 打开弹窗
    startLaunchSequence(() => setPrivacyOpen(true))
  })

  /** 「不同意」：toast 提示并保留弹窗（遮罩盖住页面，不可进主功能） */
  const refusePrivacy = (): void => {
    void Taro.showToast({ title: '需要同意后才能使用', icon: 'none', duration: 2000 })
  }

  /** 「同意并继续」：写一次性标记（launch.ts 内续跑步骤②位置授权）并关弹窗 */
  const acceptPrivacy = (): void => {
    agreePrivacy()
    setPrivacyOpen(false)
  }

  /* ---------- 导航（NAV_ITEMS 已删：登录入口并入问候区头像；装备入口在 profile） ---------- */

  const goRoutes = (): void => {
    void Taro.navigateTo({ url: ROUTES_PAGE })
  }

  const goDetail = (id: number): void => {
    void Taro.navigateTo({ url: `${DETAIL_PAGE}?id=${id}` })
  }

  /** 我的（tab 页）：reLaunch 对齐 M3TabBar 口径；游客先过 requireAuth 弹窗 */
  const goProfileTab = (): void => {
    if (!requireAuth()) return
    void Taro.reLaunch({ url: PROFILE_PAGE })
  }

  /** 问候区头像点击：已登录 → 我的；未登录 → 登录入口（weapp 一键登录 / H5 邮箱登录） */
  const goWho = (): void => {
    if (getTokenPair()) {
      void Taro.reLaunch({ url: PROFILE_PAGE })
      return
    }
    goLoginEntry()
  }

  const onBell = (): void => {
    void Taro.showToast({ title: '消息中心待后端', icon: 'none', duration: 2000 })
  }

  /* ---------- 渲染数据 ---------- */

  const authed = pair !== null
  const displayName = user?.nickname ?? '山友'
  const avatarChar = user?.nickname?.trim().charAt(0) || (authed ? '…' : '客')
  const greetText = greetByHour()

  // ⑤ hero-card：第一条路线渲染 name/distance_km（真实）；天气/匹配度沿用原型文案（mock 待后端 G-7/G-9）
  const hero = routes[0]
  const heroName = hero ? hero.name : '路线加载中…'
  const heroEm = hero ? ` · ${sportLabel(hero.sport)}` : ''
  const heroSub = hero
    ? `本周末多云 12–19℃ · ${fmtKm(hero.distance_km)}km · 与你的画像匹配 96%`
    : routesErr || '路线数据加载中…'

  // ⑥ 附近热门：取前 4 条，scene 按 s1-s4 模板轮换
  const nearRoutes = routes.slice(0, 4)

  return (
    <View className="index-page">
      <SportSprite />

      {/* ① 上半屏场景层：静态渐变场景 SVG + 同款暗化盖层（05 原型视频轮播 defer G-12） */}
      <View className="cinema-layer">
        <MountainScene gid="csky" tall />
        <View className="cinema-shade" />
      </View>

      <View className="home-content">
        {/* ② page-head：问候区（头像=登录入口）+ 铃铛 */}
        <View className="page-head">
          <View className="who" onClick={goWho}>
            <View className={`avatar${authed ? '' : ' guest'}`}>{avatarChar}</View>
            <View className="who-text">
              <Text className="who-name">嗨，{displayName} 👋</Text>
              <Text className="who-sub">{greetText} · 今日宜出行</Text>
            </View>
          </View>
          <View className="icon-btn bell" onClick={onBell} aria-label="消息中心">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
              <path d="M18 9a6 6 0 10-12 0c0 6-2.5 7.5-2.5 7.5h17S18 15 18 9z" />
              <path d="M10 20a2.2 2.2 0 004 0" />
            </svg>
          </View>
        </View>

        {/* ③ title-xl：两行主标题（em accent 斜体，同原型两行结构） */}
        <View className="title-xl">
          <Text className="tl-line">准备好你的</Text>
          <Text className="tl-line">
            <Text className="em">下一场冒险</Text> 了吗？
          </Text>
        </View>

        {/* ④ search 条 → 路线库 */}
        <View className="search" onClick={goRoutes}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
          <Text className="search-text">搜索城市、路线或问 AI「附近有什么好走的」…</Text>
          <View className="mic">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21" />
            </svg>
          </View>
        </View>

        {/* ⑤ sec「AI 为你挑选」+ hero-card 大卡 */}
        <View className="sec">
          <Text className="sec-h">AI 为你挑选</Text>
          <Text className="sec-link" onClick={goRoutes}>
            查看全部
          </Text>
        </View>
        <View className="hero-card" onClick={hero ? () => goDetail(hero.id) : undefined}>
          <MountainScene gid="hsky" />
          <View className="hero-shade" />
          <View className="hero-info">
            <Text className="hero-name">
              {heroName}
              {heroEm ? <Text className="em">{heroEm}</Text> : null}
            </Text>
            <Text className="hero-sub">{heroSub}</Text>
          </View>
          <View className="hero-fab">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 17L17 7M9 7h8v8" />
            </svg>
          </View>
          {/* mock 标注：天气/匹配度非真实数据（P2 G-7/G-9 待后端） */}
          {hero ? <Text className="mock-tag">示例</Text> : null}
        </View>

        {/* ⑥ sec「附近热门路线」+ 横滚 mini-card（前 4 条，s1-s4 场景轮换） */}
        <View className="sec">
          <Text className="sec-h">附近热门路线</Text>
          <Text className="sec-link" onClick={goRoutes}>
            全部 {routes.length} 条
          </Text>
        </View>
        <ScrollView className="hrow" scrollX>
          {nearRoutes.length === 0 ? (
            <View className="row-empty">{routesErr || '路线加载中…'}</View>
          ) : (
            nearRoutes.map((r, i) => (
              <View key={r.id} className="mini-card" onClick={() => goDetail(r.id)}>
                <MiniScene variant={i % 4} uid={`n${r.id}`} />
                <View className="m-shade" />
                <View className="m-sport">
                  <View className="mini-sport">
                    <svg className="icon">
                      <use href={`#${SPORT_ICON[r.sport] ?? 'icon-hiking'}`} />
                    </svg>
                    <Text>{sportLabel(r.sport)}</Text>
                  </View>
                </View>
                <View className="m-info">
                  <Text className="m-name">{r.name}</Text>
                  <View className="m-meta">
                    <Text>{fmtKm(r.distance_km)}km</Text>
                    <Text>↑{r.climb_m}m</Text>
                    <Text>★{r.difficulty}</Text>
                  </View>
                </View>
              </View>
            ))
          )}
        </ScrollView>

        {/* ⑦ sec「最近足迹」+ 横滚：GET /trips?status=done（真实）；空态按登录态区分 */}
        <View className="sec">
          <Text className="sec-h">最近足迹</Text>
          <Text className="sec-link" onClick={goProfileTab}>
            全部足迹
          </Text>
        </View>
        <ScrollView className="hrow" scrollX>
          {!authed ? (
            <View className="row-empty">登录后查看足迹</View>
          ) : doneTrips && doneTrips.length > 0 ? (
            doneTrips.map((t, i) => (
              <View key={t.id} className="mini-card" onClick={goProfileTab}>
                <MiniScene variant={4 + (i % 2)} uid={`t${t.id}`} />
                <View className="m-shade" />
                <View className="m-info">
                  <Text className="m-name">{t.route_name}</Text>
                  <View className="m-meta">
                    <Text>{mmdd(t.date)}</Text>
                    <Text>{fmtKm(t.distance_km)}km</Text>
                    <Text>✓已完成</Text>
                  </View>
                </View>
              </View>
            ))
          ) : (
            <View className="row-empty">完成徒步后出现在这里</View>
          )}
        </ScrollView>
      </View>

      {/* ⑧ M8 安卓形态：AI 对话 FAB（页面级，M8 决策保留）+ M3 药丸底导航 */}
      <M3Fab />
      <M3TabBar active="home" />

      {/* 启动序列①：隐私政策半屏弹窗（不同意不关闭，遮罩盖住页面不可进主功能） */}
      {privacyOpen && (
        <View className="privacy-mask">
          <View className="privacy-sheet">
            <View className="privacy-title">服务协议与隐私政策</View>
            <View className="privacy-body">
              <Text className="privacy-text">欢迎使用赶路咯！在开始使用前，请了解我们如何处理你的信息：</Text>
              <Text className="privacy-text">1. 位置信息：在你授权后获取地理位置（wgs84），仅用于路线匹配与行程定位；拒绝授权不影响核心功能的使用。</Text>
              <Text className="privacy-text">2. 登录信息：微信一键登录会使用微信登录凭证与你的微信昵称创建/识别账号；邮箱登录仅收集邮箱与昵称。</Text>
              <Text className="privacy-text">3. 你的画像、装备清单与行程数据仅用于向你提供规划服务，不会对外共享。</Text>
              <Text className="privacy-text">
                继续使用即表示你已阅读并同意
                <Text className="privacy-link">《用户协议》</Text>
                与
                <Text className="privacy-link">《隐私政策》</Text>
                。
              </Text>
            </View>
            <View className="privacy-btns">
              <View className="privacy-btn ghost" onClick={refusePrivacy}>
                不同意
              </View>
              <View className="privacy-btn primary" onClick={acceptPrivacy}>
                同意并继续
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
