/**
 * 引导 02 · 运动偏好（M7.5 Task 1，对齐原型 02-onboard-sport）：
 * - 8 运动 tiles 多选（SPORTS 元数据复用 api/profile），1–4 项约束：
 *   超 4 项提示且不选中，0 项时「继续」给出提示（可改走跳过）
 * - 「继 续」→ PUT /profile（合并既有 exp_level/fitness，PUT 是整体覆盖）
 *   → onboard/exp；「暂时跳过，先随便逛逛」→ reLaunch 首页（不写 profile）
 * - 已登录进入时 GET /profile 回显已选（profile 页「重新完成画像」再引导场景）
 * - 未登录降级态（与 gear/profile 页同款 guest-card）
 */
import { useCallback, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { getTokenPair } from '@/api/auth'
import {
  getProfile,
  putProfile,
  SPORTS,
  MAX_SPORTS,
  type ProfileOut,
  type Sport,
} from '@/api/profile'
import { HOME_PAGE, LOGIN_PAGE, ONBOARD_EXP_PAGE, type ApiError } from '@/api/client'
import './index.scss'

type PagePhase = 'checking' | 'guest' | 'ready'

export default function OnboardSport() {
  const [phase, setPhase] = useState<PagePhase>('checking')
  const [profile, setProfile] = useState<ProfileOut | null>(null)
  const [selected, setSelected] = useState<Sport[]>([])
  const [hint, setHint] = useState('')
  const [pageError, setPageError] = useState('')
  const [saving, setSaving] = useState(false)

  const loadData = useCallback(async (): Promise<void> => {
    setPageError('')
    setHint('')
    if (!getTokenPair()) {
      setPhase('guest')
      return
    }
    try {
      const p = await getProfile()
      setProfile(p)
      setSelected(p.sports ?? [])
      setPhase('ready')
    } catch (err) {
      const e = err as ApiError
      setPageError(e?.detail || String(err))
      setPhase('ready')
    }
  }, [])

  useDidShow(() => {
    void loadData()
  })

  const toggleSport = (key: Sport): void => {
    setHint('')
    if (selected.includes(key)) {
      setSelected(selected.filter((s) => s !== key))
    } else if (selected.length >= MAX_SPORTS) {
      setHint(`最多选 ${MAX_SPORTS} 项，先取消一项再换`)
    } else {
      setSelected([...selected, key])
    }
  }

  const goBack = (): void => {
    void Taro.navigateBack().catch(() => {
      void Taro.reLaunch({ url: HOME_PAGE })
    })
  }

  /* 继续：PUT 整体覆盖（exp_level/fitness 取服务端现值，避免把已填画像冲掉） */
  const goNext = async (): Promise<void> => {
    if (saving) return
    if (selected.length === 0) {
      setHint('至少选择 1 项运动，或先跳过随便逛逛')
      return
    }
    setSaving(true)
    setHint('')
    try {
      await putProfile({
        sports: selected,
        exp_level: profile?.exp_level ?? 1,
        fitness: profile?.fitness ?? 2,
      })
      await Taro.navigateTo({ url: ONBOARD_EXP_PAGE })
    } catch (err) {
      const e = err as ApiError
      setHint(e?.detail || String(err))
    } finally {
      setSaving(false)
    }
  }

  /* 跳过：不写 profile，直接回首页入口 */
  const goSkip = (): void => {
    void Taro.reLaunch({ url: HOME_PAGE })
  }

  const goLogin = (): void => {
    void Taro.reLaunch({ url: LOGIN_PAGE })
  }

  /* ---------- 未登录 / 加载态 ---------- */
  if (phase !== 'ready') {
    return (
      <View className="onboard-page">
        <View className="guest-card">
          <View className="guest-avatar">🥾</View>
          <View className="guest-title">{phase === 'checking' ? '加载中…' : '还未登录'}</View>
          <View className="guest-sub">
            {phase === 'checking' ? '正在获取你的画像' : '登录后开始三步画像引导，让推荐更合身'}
          </View>
          {phase === 'guest' && (
            <View className="btn btn-primary" onClick={goLogin}>
              去登录
            </View>
          )}
        </View>
      </View>
    )
  }

  return (
    <View className="onboard-page">
      {/* 步骤头（1/3 运动偏好）+ 进度条 */}
      <View className="step-head">
        <View className="back-btn" onClick={goBack}>
          ‹
        </View>
        <Text className="step-label">用户画像 · 1/3 运动偏好</Text>
        <View className="back-btn placeholder" />
      </View>
      <View className="stepper">
        <i className="done" />
        <i />
        <i />
      </View>

      <View className="onboard-title">
        你喜欢哪些<Text className="em">户外运动</Text>？
      </View>
      <View className="onboard-sub">
        选择 1–{MAX_SPORTS} 项，赶路咯 AI 将据此为你匹配路线类型与运动强度。
        <Text className="hl">已选 {selected.length} 项</Text>
      </View>

      {pageError && (
        <View className="onboard-hint err">
          <Text>{pageError}</Text>
        </View>
      )}

      {/* 8 运动 tiles 多选 */}
      <View className="sport-grid">
        {SPORTS.map((s) => {
          const sel = selected.includes(s.key)
          return (
            <View
              key={s.key}
              className={`icon-tile${sel ? ' sel' : ''}`}
              onClick={() => toggleSport(s.key)}
            >
              <View className="tile-emoji">{s.emoji}</View>
              <View className="tile-name">{s.label}</View>
              <View className="tile-sub">{s.sub}</View>
              <View className="tile-check">✓</View>
            </View>
          )
        })}
      </View>

      {/* 绿色提示条（对齐原型 02 notice.green） */}
      <View className="notice-green">
        <Text className="n-ico">✓</Text>
        <Text>
          运动偏好只是第一步，接下来还会请你填写
          <Text className="hl">徒步经验、体能与装备</Text>
          ，让路线推荐更安全。
        </Text>
      </View>

      {hint && (
        <View className="onboard-hint">
          <Text>{hint}</Text>
        </View>
      )}

      {/* 底部固定 CTA：继续 / 跳过 */}
      <View className="cta-wrap">
        <View className={`btn btn-primary${saving ? ' is-loading' : ''}`} onClick={() => void goNext()}>
          {saving ? '保存中…' : '继 续'}
        </View>
        <View className="cta-skip">
          暂时跳过，<Text className="skip-link" onClick={goSkip}>先随便逛逛</Text>
        </View>
      </View>
    </View>
  )
}
