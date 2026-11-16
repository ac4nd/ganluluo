/**
 * 引导 03 · 经验与体能（M7.5 Task 1，对齐原型 03-onboard-exp）：
 * - 经验 4 档单选（EXP_LEVELS 1-4）/ 体能 5 档单选（FITNESS_LEVELS 1-5，
 *   档位文案与原型 03 一致；体能行带 5 格 meter 可视化）
 * - GET /profile 回显（sports 由服务端现值随 PUT 带回，不改动 02 的选择）
 * - 「完成画像」→ PUT /profile → onboard/gear（04 装备清单，完成后再回首页）
 */
import { useCallback, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { getTokenPair } from '@/api/auth'
import { getProfile, putProfile, EXP_LEVELS, FITNESS_LEVELS, type ProfileOut } from '@/api/profile'
import { LOGIN_PAGE, ONBOARD_SPORT_PAGE, type ApiError } from '@/api/client'
import './index.scss'

type PagePhase = 'checking' | 'guest' | 'ready'

export default function OnboardExp() {
  const [phase, setPhase] = useState<PagePhase>('checking')
  const [profile, setProfile] = useState<ProfileOut | null>(null)
  const [expLevel, setExpLevel] = useState(1)
  const [fitness, setFitness] = useState(2)
  const [pageError, setPageError] = useState('')
  const [hint, setHint] = useState('')
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
      setExpLevel(p.exp_level ?? 1)
      setFitness(p.fitness ?? 2)
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

  const goBack = (): void => {
    void Taro.navigateBack().catch(() => {
      void Taro.reLaunch({ url: ONBOARD_SPORT_PAGE })
    })
  }

  /* 完成画像：PUT 整体覆盖（sports 原样带回服务端现值）→ 04 装备清单 */
  const finish = async (): Promise<void> => {
    if (saving) return
    setSaving(true)
    setHint('')
    try {
      await putProfile({
        sports: profile?.sports ?? [],
        exp_level: expLevel,
        fitness,
      })
      await Taro.navigateTo({ url: '/pages/gear/index' })
    } catch (err) {
      const e = err as ApiError
      setHint(e?.detail || String(err))
    } finally {
      setSaving(false)
    }
  }

  const goLogin = (): void => {
    void Taro.reLaunch({ url: LOGIN_PAGE })
  }

  /* ---------- 未登录 / 加载态 ---------- */
  if (phase !== 'ready') {
    return (
      <View className="onboard-page">
        <View className="guest-card">
          <View className="guest-avatar">💪</View>
          <View className="guest-title">{phase === 'checking' ? '加载中…' : '还未登录'}</View>
          <View className="guest-sub">
            {phase === 'checking' ? '正在获取你的画像' : '登录后继续完成画像引导'}
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
      {/* 步骤头（2/3 经验与体能）+ 进度条 */}
      <View className="step-head">
        <View className="back-btn" onClick={goBack}>
          ‹
        </View>
        <Text className="step-label">用户画像 · 2/3 经验与体能</Text>
        <View className="back-btn placeholder" />
      </View>
      <View className="stepper">
        <i className="done" />
        <i className="done" />
        <i />
      </View>

      <View className="onboard-title">
        你的<Text className="em">徒步经验</Text>与体能如何？
      </View>
      <View className="onboard-sub">
        AI 会用它来估算配速、控制单日里程，并过滤超出能力范围的路线。
      </View>

      {pageError && (
        <View className="onboard-hint err">
          <Text>{pageError}</Text>
        </View>
      )}

      {/* 经验 4 档单选 */}
      <View className="sec">
        <Text className="sec-title">🥾 徒步经验</Text>
      </View>
      <View className="option-group">
        {EXP_LEVELS.map((x) => (
          <View
            key={x.value}
            className={`option${expLevel === x.value ? ' sel' : ''}`}
            onClick={() => setExpLevel(x.value)}
          >
            <View className="radio" />
            <View className="option-text">
              <View className="option-title">{x.label}</View>
              <View className="option-sub">{x.sub}</View>
            </View>
          </View>
        ))}
      </View>

      {/* 体能 5 档单选（带 5 格 meter） */}
      <View className="sec">
        <Text className="sec-title">💪 体能自评</Text>
      </View>
      <View className="option-group">
        {FITNESS_LEVELS.map((x) => (
          <View
            key={x.value}
            className={`option${fitness === x.value ? ' sel' : ''}`}
            onClick={() => setFitness(x.value)}
          >
            <View className="radio" />
            <View className="option-text">
              <View className="option-title">{x.label}</View>
              <View className="option-sub">{x.sub}</View>
              <View className="meter">
                {[1, 2, 3, 4, 5].map((i) => (
                  <i key={i} className={i <= x.value ? 'on' : ''} />
                ))}
              </View>
            </View>
          </View>
        ))}
      </View>

      {hint && (
        <View className="onboard-hint">
          <Text>{hint}</Text>
        </View>
      )}

      {/* 底部固定 CTA：完成画像 */}
      <View className="cta-wrap">
        <View className={`btn btn-primary${saving ? ' is-loading' : ''}`} onClick={() => void finish()}>
          {saving ? '保存中…' : '完成画像'}
        </View>
        <View className="cta-skip">经验与体能仅用于推荐计算，可随时在「我的」中修改</View>
      </View>
    </View>
  )
}
