/**
 * M8 Task 3 · 安卓 Material 3 共享组件（形态逐元素对照 protype/a-home.html）：
 * - M3TabBar：整宽贴底导航（4 tab 图标+文字；选中态 = accent 药丸底托住图标，
 *   对齐 a-home .nav-md 的药丸指示器形态）。首页/路线库/行程/我的四个主页面共用；
 *   自绘导航不走原生 tabBar，tab 切换用 reLaunch（同时防 navigateTo 路由栈超限）。
 * - M3Fab：AI 对话悬浮入口（56dp 渐变圆角钮 + sparkle 图标 + 阴影，浮于底导航
 *   上方右下角，对齐 a-home .fab）；对话页自身不渲染。
 * 纯 UI/导航组件，不带业务状态；未登录点受限 tab / FAB 统一 reLaunch 登录页
 * （与 index 页 go() 的路由守卫同口径）。
 */
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import { getTokenPair, HOME_PAGE, LOGIN_PAGE } from '@/api/client'
import './m3.scss'

export type M3Tab = 'home' | 'routes' | 'trips' | 'profile'

const CHAT_PAGE = '/pages/chat/index'
const ROUTES_PAGE = '/pages/routes/index'
const TRIPS_PAGE = '/pages/trips/index'
const PROFILE_PAGE = '/pages/profile/index'

/** a-home .nav-md 图标（24×24 线性 · currentColor · stroke 1.8），18dp → 36px 双倍稿 */
const strokeProps = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

interface TabDef {
  key: M3Tab
  label: string
  url: string
  /** 需要登录的 tab（行程 / 我的；首页与路线库公开） */
  authed: boolean
  icon: JSX.Element
}

const TABS: TabDef[] = [
  {
    key: 'home',
    label: '首页',
    url: HOME_PAGE,
    authed: false,
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" {...strokeProps}>
        <path d="M3.5 10.5L12 4l8.5 6.5V20a1.5 1.5 0 01-1.5 1.5h-4.5v-6h-5v6H5A1.5 1.5 0 013.5 20z" />
      </svg>
    ),
  },
  {
    key: 'routes',
    label: '路线',
    url: ROUTES_PAGE,
    authed: false,
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" {...strokeProps}>
        <circle cx="6" cy="18" r="2.4" />
        <circle cx="18" cy="6" r="2.4" />
        <path d="M8.2 16.4C13 13.5 9.8 8.6 15.8 7.6" />
      </svg>
    ),
  },
  {
    key: 'trips',
    label: '行程',
    url: TRIPS_PAGE,
    authed: true,
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" {...strokeProps}>
        <rect x="4" y="5" width="16" height="15" rx="3" />
        <path d="M4 10h16M8 3v4M16 3v4" />
      </svg>
    ),
  },
  {
    key: 'profile',
    label: '我的',
    url: PROFILE_PAGE,
    authed: true,
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" {...strokeProps}>
        <circle cx="12" cy="8" r="3.6" />
        <path d="M5 20a7 7 0 0114 0" />
      </svg>
    ),
  },
]

/** tab 切换：受限 tab 未登录 → 登录页；目标即当前页时 no-op 防自跳 */
function goTab(tab: TabDef): void {
  if (tab.authed && !getTokenPair()) {
    void Taro.reLaunch({ url: LOGIN_PAGE })
    return
  }
  void Taro.reLaunch({ url: tab.url })
}

export function M3TabBar({ active }: { active: M3Tab }): JSX.Element {
  return (
    <View className="m3-nav">
      {TABS.map((t) => (
        <View
          key={t.key}
          className={`m3-nav-item${active === t.key ? ' on' : ''}`}
          onClick={() => goTab(t)}
          aria-label={t.label}
        >
          <View className="pill">{t.icon}</View>
          <Text>{t.label}</Text>
        </View>
      ))}
    </View>
  )
}

/** a-home .fab 图标：sparkle（大四角星 + 小星） */
function sparkleIcon(): JSX.Element {
  return (
    <svg width="44" height="44" viewBox="0 0 24 24" {...strokeProps} strokeWidth="1.9">
      <path d="M12 4l1.8 4.7L18.5 10.5l-4.7 1.8L12 17l-1.8-4.7L5.5 10.5l4.7-1.8z" />
      <path d="M18.8 15.6l.7 1.7 1.7.7-1.7.7-.7 1.7-.7-1.7-1.7-.7 1.7-.7z" />
    </svg>
  )
}

export function M3Fab(): JSX.Element {
  const goChat = (): void => {
    if (!getTokenPair()) {
      void Taro.reLaunch({ url: LOGIN_PAGE })
      return
    }
    void Taro.navigateTo({ url: CHAT_PAGE })
  }
  return (
    <View className="m3-fab" onClick={goChat} aria-label="AI 规划">
      {sparkleIcon()}
    </View>
  )
}
