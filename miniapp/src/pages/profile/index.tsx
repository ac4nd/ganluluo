/**
 * 我的页（M7 Task 2）：
 * - /auth/me 昵称 + GET /profile 画像（运动多选 tiles + 经验 1-4 / 体能 1-5 选择器，保存按钮批量 PUT）
 * - 额度卡 GET /assistant/quota（对齐原型 09 quota-card 双态：
 *   trial 中性徽章 + 金色升级按钮；vip 金边 + 金徽章 + 管理续费；
 *   双进度条 warn>=60% / danger>=85% 三级色）
 * - 未登录降级态（引导去登录）；退出登录（吊销 + 清 storage + reLaunch login）
 */
import { useCallback, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { logout, me, getTokenPair, type UserOut } from '@/api/auth'
import { quota, type UsageOut } from '@/api/assistant'
import type { ApiError } from '@/api/client'
import {
  getProfile,
  putProfile,
  EXP_LEVELS,
  FITNESS_LEVELS,
  SPORTS,
  type ProfileOut,
  type Sport,
} from '@/api/profile'
import { LOGIN_PAGE, ONBOARD_SPORT_PAGE } from '@/api/client'
import './index.scss'

type PagePhase = 'checking' | 'guest' | 'ready'

type QuotaLevel = '' | 'warn' | 'danger'

/** token 用量文案：>=1w 显示 k（对齐原型 fmt） */
function fmtTokens(n: number): string {
  return n >= 10000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n)
}

/**
 * 用量比例 → 进度条档色（对齐原型 cls：>=0.85 danger / >=0.6 warn）。
 * limit<=0 的防御分支与宽度计算（qbar-fill 0%）统一为中性：后端正常恒发正数限额，
 * 真触发时渲染灰空条 + 「x / 0」，不误报红色 danger。
 */
function levelOf(used: number, limit: number): QuotaLevel {
  if (limit <= 0) return ''
  const r = used / limit
  return r >= 0.85 ? 'danger' : r >= 0.6 ? 'warn' : ''
}

export default function Profile() {
  const [phase, setPhase] = useState<PagePhase>('checking')
  const [user, setUser] = useState<UserOut | null>(null)
  const [profile, setProfile] = useState<ProfileOut | null>(null)
  const [sports, setSports] = useState<Sport[]>([])
  const [expLevel, setExpLevel] = useState(1)
  const [fitness, setFitness] = useState(2)
  const [quotaInfo, setQuotaInfo] = useState<UsageOut | null>(null)
  const [pageError, setPageError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  const loadData = useCallback(async (): Promise<void> => {
    setPageError('')
    setSaveMsg('')
    if (!getTokenPair()) {
      setPhase('guest')
      return
    }
    setPhase('ready')
    const results = await Promise.allSettled([me(), getProfile(), quota()])
    if (results[0].status === 'fulfilled') setUser(results[0].value)
    if (results[1].status === 'fulfilled') {
      const p = results[1].value
      setProfile(p)
      setSports(p.sports)
      setExpLevel(p.exp_level)
      setFitness(p.fitness)
    }
    if (results[2].status === 'fulfilled') setQuotaInfo(results[2].value)
    const failed = results.find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined
    if (failed) {
      const e = failed.reason as ApiError
      setPageError(e?.detail || String(failed.reason))
    }
  }, [])

  // 每次进页面都刷新（从装备页/登录页返回时同步最新状态）
  useDidShow(() => {
    void loadData()
  })

  const toggleSport = (key: Sport): void => {
    setSaveMsg('')
    setSports((cur) => (cur.includes(key) ? cur.filter((s) => s !== key) : [...cur, key]))
  }

  const saveProfile = async (): Promise<void> => {
    if (saving) return
    setSaving(true)
    setSaveMsg('')
    try {
      const saved = await putProfile({ sports, exp_level: expLevel, fitness })
      setProfile(saved)
      setSports(saved.sports)
      setExpLevel(saved.exp_level)
      setFitness(saved.fitness)
      setSaveMsg('画像已保存')
    } catch (err) {
      const e = err as ApiError
      setSaveMsg(`保存失败：${e?.detail || String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  const doLogout = async (): Promise<void> => {
    await logout() // 无论成败本地一律清登录态（api/auth.logout）
    void Taro.reLaunch({ url: LOGIN_PAGE })
  }

  const goLogin = (): void => {
    void Taro.reLaunch({ url: LOGIN_PAGE })
  }

  const goGear = (): void => {
    void Taro.navigateTo({ url: '/pages/gear/index' })
  }

  /* 重新完成画像：从 02 运动偏好开始走三步引导 */
  const goReOnboard = (): void => {
    void Taro.navigateTo({ url: ONBOARD_SPORT_PAGE })
  }

  /* ---------- 未登录降级态 ---------- */
  if (phase !== 'ready') {
    return (
      <View className="profile-page">
        <View className="guest-card">
          <View className="guest-avatar">?</View>
          <View className="guest-title">{phase === 'checking' ? '加载中…' : '还未登录'}</View>
          <View className="guest-sub">
            {phase === 'checking'
              ? '正在获取你的画像与额度'
              : '登录后可编辑运动偏好、经验体能与装备清单'}
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

  /* ---------- 额度卡双态（trial / vip） ---------- */
  const isVip = quotaInfo?.tier === 'vip'
  const chatsLevel = quotaInfo ? levelOf(quotaInfo.chats_used, quotaInfo.daily_chats_limit) : ''
  const tokensLevel = quotaInfo ? levelOf(quotaInfo.tokens_used, quotaInfo.daily_tokens_limit) : ''
  const chatsPct = quotaInfo && quotaInfo.daily_chats_limit > 0
    ? Math.min(100, Math.round((quotaInfo.chats_used / quotaInfo.daily_chats_limit) * 100))
    : 0
  const tokensPct = quotaInfo && quotaInfo.daily_tokens_limit > 0
    ? Math.min(100, Math.round((quotaInfo.tokens_used / quotaInfo.daily_tokens_limit) * 100))
    : 0
  const nickname = user?.nickname || '山友'
  const expMeta = EXP_LEVELS.find((x) => x.value === profile?.exp_level)
  const fitMeta = FITNESS_LEVELS.find((x) => x.value === profile?.fitness)

  return (
    <View className="profile-page">
      {/* 顶部：头像 + 昵称 + 画像标签 */}
      <View className="profile-top">
        <View className="avatar-lg">{nickname.slice(0, 1)}</View>
        <View className="profile-meta">
          <View className="profile-name">{nickname}</View>
          <View className="profile-tags">
            {expMeta && <Text className="tag">{expMeta.label}</Text>}
            {fitMeta && <Text className="tag amber">体能 · {fitMeta.label}</Text>}
          </View>
        </View>
      </View>

      {pageError && (
        <View className="profile-error">
          <Text>{pageError}</Text>
        </View>
      )}

      {/* 额度卡（GET /assistant/quota） */}
      <View className={`quota-card${isVip ? ' vip' : ''}`}>
        <View className="qc-title">
          <View className="qc-ic">✦</View>
          <Text className="qc-name">AI 助手额度</Text>
          <Text className={`badge-tier ${isVip ? 'vip' : 'trial'}`}>{isVip ? 'VIP 会员' : '试用版'}</Text>
        </View>
        <View className="qc-reset">
          {quotaInfo
            ? `每日 00:00 重置 · ${isVip ? 'VIP 每日 50 次对话 / 50 万 Token' : '试用版每日 5 次对话 / 2 万 Token'}`
            : '额度信息加载中…'}
        </View>
        {quotaInfo && (
          <>
            <View className="qrow">
              <Text>今日对话</Text>
              <Text className="qval">{quotaInfo.chats_used} / {quotaInfo.daily_chats_limit} 次</Text>
            </View>
            <View className={`qbar ${chatsLevel}`}>
              <View className="qbar-fill" style={{ width: `${chatsPct}%` }} />
            </View>
            <View className="qrow">
              <Text>今日 Token</Text>
              <Text className="qval">
                {fmtTokens(quotaInfo.tokens_used)} / {fmtTokens(quotaInfo.daily_tokens_limit)}
              </Text>
            </View>
            <View className={`qbar ${tokensLevel}`}>
              <View className="qbar-fill" style={{ width: `${tokensPct}%` }} />
            </View>
            <View className="qc-foot">
              <Text className="qc-note">
                {isVip ? '进行中徒步可无限次召唤实况助手' : '额度用尽后 AI 规划次日恢复'}
              </Text>
              <View className="btn-up">{isVip ? '管理续费' : '升级 VIP'}</View>
            </View>
          </>
        )}
      </View>

      {/* 运动偏好 tiles（多选） */}
      <View className="sec">
        <Text className="sec-title">我的运动偏好</Text>
        <Text className="sec-link">可多选</Text>
      </View>
      <View className="sport-grid">
        {SPORTS.map((s) => {
          const sel = sports.includes(s.key)
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

      {/* 经验 1-4 选择器 */}
      <View className="sec">
        <Text className="sec-title">🥾 徒步经验</Text>
      </View>
      <View className="option-group">
        {EXP_LEVELS.map((x) => (
          <View
            key={x.value}
            className={`option${expLevel === x.value ? ' sel' : ''}`}
            onClick={() => {
              setSaveMsg('')
              setExpLevel(x.value)
            }}
          >
            <View className="radio" />
            <View className="option-text">
              <View className="option-title">{x.label}</View>
              <View className="option-sub">{x.sub}</View>
            </View>
          </View>
        ))}
      </View>

      {/* 体能 1-5 选择器 */}
      <View className="sec">
        <Text className="sec-title">💪 体能自评</Text>
      </View>
      <View className="option-group">
        {FITNESS_LEVELS.map((x) => (
          <View
            key={x.value}
            className={`option${fitness === x.value ? ' sel' : ''}`}
            onClick={() => {
              setSaveMsg('')
              setFitness(x.value)
            }}
          >
            <View className="radio" />
            <View className="option-text">
              <View className="option-title">{x.label}</View>
              <View className="option-sub">{x.sub}</View>
            </View>
          </View>
        ))}
      </View>

      {/* 保存（批量 PUT /profile） */}
      <View
        className={`btn btn-primary${saving ? ' is-loading' : ''}`}
        onClick={saveProfile}
      >
        {saving ? '保存中…' : '保存画像'}
      </View>
      {saveMsg && <View className="save-msg">{saveMsg}</View>}

      {/* 装备清单入口 + 重新完成画像入口 */}
      <View className="sec">
        <Text className="sec-title">常用装备</Text>
      </View>
      <View className="row-item" onClick={goGear}>
        <View className="row-ic">🎒</View>
        <Text className="row-t">装备清单</Text>
        <Text className="row-s">编辑 ›</Text>
      </View>
      <View className="row-item re-onboard" onClick={goReOnboard}>
        <View className="row-ic">🧭</View>
        <Text className="row-t">重新完成画像</Text>
        <Text className="row-s">三步引导 ›</Text>
      </View>

      {/* 退出登录 */}
      <View className="btn btn-ghost logout-btn" onClick={doLogout}>
        退出登录
      </View>
    </View>
  )
}
