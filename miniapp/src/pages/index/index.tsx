/**
 * 入口/导航页（M7 Task 2 改造，原 Task 1 脚手架占位页）：
 * - 展示登录态（getTokenPair → /auth/me 拉昵称）
 * - 已登录：用户摘要 + 各页导航链接（我的 / 装备清单；AI 对话、路线为 Task 3/4 占位）
 * - 未登录：显示「去登录」按钮
 * - M8 Task 2：useDidShow 触发启动序列（launch.ts，一次冷启动一次）——
 *   首次启动弹自定义半屏隐私弹窗（同意后触发位置授权；不同意保留弹窗不可进主功能）
 * 完整路由守卫在 Task 3/4 业务页接入时用 auth.ts 的 getTokenPair 判断。
 */
import { useCallback, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { me, getTokenPair, type UserOut } from '@/api/auth'
import { LOGIN_PAGE, type ApiError, type TokenPair } from '@/api/client'
import { agreePrivacy, startLaunchSequence } from '@/launch'
import './index.scss'

interface NavItem {
  title: string
  desc: string
  url: string
  ready: boolean
}

const NAV_ITEMS: NavItem[] = [
  { title: '我的', desc: '画像编辑 + AI 额度卡', url: '/pages/profile/index', ready: true },
  { title: '装备清单', desc: '勾选常用装备，参与路线匹配', url: '/pages/gear/index', ready: true },
  { title: '登录 / 注册', desc: '邮箱 + 密码', url: LOGIN_PAGE, ready: true },
  { title: '路线库', desc: '筛选 + 路线详情 + 加入计划', url: '/pages/routes/index', ready: true },
  { title: 'AI 规划对话', desc: 'SSE 流式问答 + 配额环 + 一键生成计划', url: '/pages/chat/index', ready: true },
  { title: '行程计划', desc: '进行中 / 足迹 + 装备提醒', url: '/pages/trips/index', ready: true },
]

export default function Index() {
  const [pair, setPair] = useState<TokenPair | null>(null)
  const [user, setUser] = useState<UserOut | null>(null)
  // 启动序列①：首次启动（gl_privacy_ok 无值）弹半屏隐私弹窗
  const [privacyOpen, setPrivacyOpen] = useState(false)

  const refresh = useCallback(async (): Promise<void> => {
    const cur = getTokenPair()
    setPair(cur)
    if (!cur) {
      setUser(null)
      return
    }
    try {
      setUser(await me())
    } catch (err) {
      const e = err as ApiError
      console.warn('[index] /auth/me 失败:', e?.detail)
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

  const go = (item: NavItem): void => {
    if (!item.ready) return
    // 未登录业务页统一去登录页；登录页自己也可以直达
    if (item.url !== LOGIN_PAGE && !getTokenPair()) {
      void Taro.reLaunch({ url: LOGIN_PAGE })
      return
    }
    if (item.url === LOGIN_PAGE && getTokenPair()) {
      void Taro.reLaunch({ url: '/pages/profile/index' })
      return
    }
    void Taro.navigateTo({ url: item.url })
  }

  return (
    <View className="index-page">
      <View className="hero-card">
        <View className="hero-label">GANLULUO · M7 轻端</View>
        <View className="hero-title">
          赶路咯 <Text className="em">入口</Text>
        </View>
        <View className="hero-sub">
          Taro 4 + React 18 + TS；已接入登录、我的（额度卡）、装备清单、路线库/详情、AI 对话（SSE 流式）与行程计划。
        </View>
      </View>

      {/* 登录态摘要 */}
      <View className="auth-card">
        {pair ? (
          <>
            <View className="auth-dot on" />
            <View className="auth-text">
              <Text className="auth-line">
                已登录：{user ? user.nickname : '…'}
                {user?.email ? <Text className="auth-mail">（{user.email}）</Text> : null}
              </Text>
            </View>
          </>
        ) : (
          <>
            <View className="auth-dot" />
            <View className="auth-text">
              <Text className="auth-line">未登录</Text>
              <Text className="auth-mail">部分页面需要登录后使用</Text>
            </View>
            <View className="btn-login" onClick={() => go(NAV_ITEMS[2])}>
              去登录
            </View>
          </>
        )}
      </View>

      {/* 页面导航 */}
      <View className="nav-list">
        {NAV_ITEMS.map((item) => (
          <View
            key={item.title}
            className={`nav-item${item.ready ? '' : ' disabled'}`}
            onClick={() => go(item)}
          >
            <View className="nav-text">
              <Text className="nav-title">{item.title}</Text>
              <Text className="nav-desc">{item.desc}</Text>
            </View>
            <Text className="nav-arrow">{item.ready ? '›' : '…'}</Text>
          </View>
        ))}
      </View>

      <View className="index-foot">dev 提示：H5 走 devServer 同源代理 → 本地 uvicorn 8123</View>

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
