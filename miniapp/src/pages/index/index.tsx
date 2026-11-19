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
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Image, ScrollView, Text, Video, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { me, getTokenPair, type UserOut } from '@/api/auth'
import { apiBaseUrl, type ApiError, type TokenPair } from '@/api/client'
import { goLoginEntry, requireAuth } from '@/api/guard'
import { listRoutes, type RouteOut } from '@/api/routes'
import { listTrips, type TripPlanCard } from '@/api/trips'
import { SPORTS } from '@/api/profile'
import { agreePrivacy, startLaunchSequence } from '@/launch'
import { M3Fab, M3TabBar } from '@/components/m3'
import { miniSceneUri, mountainSceneUri, sportIconUri } from './scenes'
import './index.scss'

const ROUTES_PAGE = '/pages/routes/index'
const DETAIL_PAGE = '/pages/route-detail/index'
const PROFILE_PAGE = '/pages/profile/index'

/* ① 首页背景风景视频：05 原型 13 地貌（cinema.js 同款优先级序），src 走后端
   /static 托管（weapp 绝对地址/开发者工具；H5 同源代理），生产换对象存储/CDN（G-12）。 */
const CINEMA_VIDEOS = [
  'l-snow', 'l-danxia', 'l-desert', 'l-waterfall', 'l-volcano', 'l-karst',
  'l-plateaulake', 'l-fjord', 'l-granite', 'l-peakforest', 'l-faultblock',
  'l-meadow', 'l-grassland',
]

/**
 * 横滚容器（构建期平台分支）：
 * - weapp：官方 scroll-view（scrollX）——普通 View 的 CSS overflow 在小程序不滚动；
 * - H5：普通 View + CSS overflow-x + 桌面鼠标拖拽滚动（pointer 按下平移 scrollLeft；
 *   触屏浏览器走原生触摸滚动，pointerType!=='mouse' 不启用以免叠加抖动）。
 *   Taro H5 ScrollView 是 Stencil Web Component，其 slot 投影在 useDidShow 重渲染后
 *   重建，会破坏 inline-block 布局（卡片纵排 bug），故 H5 不用 ScrollView。
 * TARO_ENV 被构建期静态替换，双端产物各自只含一个分支。
 */
function HRow({ children }: { children: ReactNode }) {
  const scroller = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (process.env.TARO_ENV !== 'h5') return
    const el = scroller.current
    if (!el) return
    let down = false
    let startX = 0
    let startLeft = 0
    const onDown = (e: PointerEvent): void => {
      if (e.pointerType !== 'mouse') return
      down = true
      startX = e.clientX
      startLeft = el.scrollLeft
    }
    const onMove = (e: PointerEvent): void => {
      if (!down) return
      el.scrollLeft = startLeft - (e.clientX - startX)
    }
    const onUp = (): void => {
      down = false
    }
    el.addEventListener('pointerdown', onDown)
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      el.removeEventListener('pointerdown', onDown)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [])

  if (process.env.TARO_ENV === 'weapp') {
    return (
      <ScrollView className="hrow" scrollX>
        {children}
      </ScrollView>
    )
  }
  return (
    <View className="hrow" ref={scroller as never}>
      {children}
    </View>
  )
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

  /* ① 背景视频轮播：乐观渲染——Video 始终挂载（若条件渲染则永不触发 onPlay，
     状态机死锁，这正是上一版不播的根因）；底层垫静态场景图，视频加载失败
     （onError）才卸载 Video 露出兜底。首轮按高对比地貌优先级，之后随机；
     切换时 cinema-fade 黑场过渡（原型同款）防闪跳。 */
  const [videoIdx, setVideoIdx] = useState(0)
  const [videoFailed, setVideoFailed] = useState(false)
  const [firstRound, setFirstRound] = useState(true)
  const [fading, setFading] = useState(false)

  const nextVideo = (): void => {
    setFading(true) // 黑场盖层先合上，500ms 后换片再掀开
    window.setTimeout(() => {
      setVideoIdx((i) => {
        if (firstRound) {
          // 首轮走完优先级清单 → 进入随机轮播（可重复地貌）
          if (i >= CINEMA_VIDEOS.length - 1) setFirstRound(false)
          return (i + 1) % CINEMA_VIDEOS.length
        }
        return Math.floor(Math.random() * CINEMA_VIDEOS.length)
      })
      window.setTimeout(() => setFading(false), 150)
    }, 500)
  }

  return (
    <View className="index-page">
      {/* ① 上半屏场景层：风景视频轮播（05 原型 cinema 行为：muted 自动播放、
          onEnded 轮换）；加载失败 → 卸载 Video 露出底层静态渐变场景兜底
          （SVG data URI + Image，weapp 不支持内联 svg 故走 Image）。 */}
      <View className="cinema-layer">
        <Image className="scene" mode="aspectFill" src={mountainSceneUri(true)} />
        {!videoFailed && (
          <Video
            className="cinema-video"
            src={`${apiBaseUrl()}/static/videos/${CINEMA_VIDEOS[videoIdx]}.mp4`}
            autoplay
            muted
            loop={false}
            objectFit="cover"
            onEnded={nextVideo}
            onError={() => setVideoFailed(true)}
          />
        )}
        <View className={`cinema-fade${fading ? ' on' : ''}`} />
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
          <Image className="scene" mode="aspectFill" src={mountainSceneUri(false)} />
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
        {/* 横滚容器见 HRow 注释（weapp scroll-view / H5 CSS overflow 双分支） */}
        <HRow>
          {nearRoutes.length === 0 ? (
            <View className="row-empty">{routesErr || '路线加载中…'}</View>
          ) : (
            nearRoutes.map((r, i) => (
              <View key={r.id} className="mini-card" onClick={() => goDetail(r.id)}>
                <Image className="scene" mode="aspectFill" src={miniSceneUri(i % 4)} />
                <View className="m-shade" />
                <View className="m-sport">
                  <View className="mini-sport">
                    <Image className="icon" src={sportIconUri(r.sport)} />
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
        </HRow>

        {/* ⑦ sec「最近足迹」+ 横滚：GET /trips?status=done（真实）；空态按登录态区分 */}
        <View className="sec">
          <Text className="sec-h">最近足迹</Text>
          <Text className="sec-link" onClick={goProfileTab}>
            全部足迹
          </Text>
        </View>
        <HRow>
          {!authed ? (
            <View className="row-empty">登录后查看足迹</View>
          ) : doneTrips && doneTrips.length > 0 ? (
            doneTrips.map((t, i) => (
              <View key={t.id} className="mini-card" onClick={goProfileTab}>
                <Image className="scene" mode="aspectFill" src={miniSceneUri(4 + (i % 2))} />
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
        </HRow>
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
