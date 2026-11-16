/**
 * 行程页（M7 Task 4，对齐原型 07-plan-trip 的计划卡语义）：
 * - tab：planned（进行中）/ done（足迹）→ GET /trips?status=
 * - TripPlanCard 卡：route_name / date（日期徽章 + 星期）/ meet_at / meet_place / region /
 *   ★difficulty / distance_km / climb_m / duration_h + gear_missing.length 条装备提醒
 *   （item_key 经装备目录翻译中文 label，失败回退原文）
 * - 卡操作：planned → 「标记完成」（PATCH status=done）+「删除」（确认后 DELETE）；
 *   done → 「删除」
 * - 空态：「还没有行程计划，去 AI 对话生成 →」（跳 /pages/chat）
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import { deleteTrip, listTrips, updateTripStatus, type TripPlanCard, type TripStatus } from '@/api/trips'
import { getCatalog } from '@/api/gear'
import { getTokenPair, LOGIN_PAGE, type ApiError } from '@/api/client'
import './index.scss'

const CHAT_PAGE = '/pages/chat/index'

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** date "2026-11-21" → { day:'21', mon:'11月', week:'周六' }；解析失败回退原文 */
function dateBadge(date: string): { day: string; mon: string; week: string } {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!m) return { day: date, mon: '', week: '' }
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return {
    day: String(Number(m[3])),
    mon: `${Number(m[2])}月`,
    week: WEEKDAYS[d.getDay()] ?? '',
  }
}

/** meet_at "08:00:00" → "08:00" */
const fmtMeet = (t: string): string => (t.length >= 5 ? t.slice(0, 5) : t)

const fmtNum = (v: number): string => v.toFixed(1).replace(/\.0$/, '')

export default function Trips() {
  const [tab, setTab] = useState<TripStatus>('planned')
  const [trips, setTrips] = useState<TripPlanCard[]>([])
  const [counts, setCounts] = useState<{ planned: number; done: number }>({ planned: 0, done: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [gearLabels, setGearLabels] = useState<Record<string, string>>({})
  /** 正在被单卡操作（完成/删除）锁住的 trip id，防重复提交 */
  const [busyId, setBusyId] = useState<number | null>(null)
  const aliveRef = useRef(true)

  useEffect(() => {
    aliveRef.current = true
    // 装备目录只用于把 gear_missing 的 item_key 翻译成中文 label（公开端点，失败回退原文）
    getCatalog()
      .then((cat) => {
        const map: Record<string, string> = {}
        for (const it of cat.items) map[it.key] = it.label
        if (aliveRef.current) setGearLabels(map)
      })
      .catch(() => undefined)
    return () => {
      aliveRef.current = false
    }
  }, [])

  const load = useCallback(async (t: TripStatus = tab): Promise<void> => {
    if (!getTokenPair()) {
      void Taro.reLaunch({ url: LOGIN_PAGE })
      return
    }
    setLoading(true)
    setError('')
    try {
      const [cur, other] = await Promise.all([
        listTrips({ status: t }),
        listTrips({ status: t === 'planned' ? 'done' : 'planned' }),
      ])
      if (!aliveRef.current) return
      setTrips(cur)
      setCounts(
        t === 'planned'
          ? { planned: cur.length, done: other.length }
          : { planned: other.length, done: cur.length },
      )
    } catch (err) {
      const e = err as ApiError
      if (aliveRef.current) setError(e?.detail || String(err))
    } finally {
      if (aliveRef.current) setLoading(false)
    }
  }, [tab])

  useDidShow(() => {
    void load()
  })

  const switchTab = (t: TripStatus): void => {
    if (t === tab) return
    setTab(t)
    void load(t)
  }

  const markDone = async (trip: TripPlanCard): Promise<void> => {
    if (busyId !== null) return
    setBusyId(trip.id)
    try {
      await updateTripStatus(trip.id, 'done')
      void Taro.showToast({ title: '已标记完成', icon: 'success', duration: 1200 })
      await load()
    } catch (err) {
      const e = err as ApiError
      void Taro.showToast({ title: e?.detail || '操作失败', icon: 'none' })
    } finally {
      setBusyId(null)
    }
  }

  const removeTrip = (trip: TripPlanCard): void => {
    if (busyId !== null) return
    void Taro.showModal({
      title: '删除行程',
      content: `确定删除「${trip.route_name}」的计划吗？`,
      confirmText: '删除',
      confirmColor: '#ff6d5a',
    })
      .then(async (res) => {
        if (!res.confirm) return
        setBusyId(trip.id)
        try {
          await deleteTrip(trip.id)
          void Taro.showToast({ title: '已删除', icon: 'success', duration: 1200 })
          await load()
        } catch (err) {
          const e = err as ApiError
          void Taro.showToast({ title: e?.detail || '删除失败', icon: 'none' })
        } finally {
          setBusyId(null)
        }
      })
      .catch(() => undefined)
  }

  const goChat = (): void => {
    void Taro.navigateTo({ url: CHAT_PAGE }).catch(() => undefined)
  }

  const renderCard = (t: TripPlanCard): JSX.Element => {
    const db = dateBadge(t.date)
    const isDone = t.status === 'done'
    return (
      <View key={t.id} className={`trip-card${isDone ? ' done' : ''}`}>
        <View className="trip-head">
          <View className="d-badge">
            <Text className="d-day">{db.day}</Text>
            <Text className="d-mon">{db.mon ? `${db.mon} ${db.week}`.trim() : ''}</Text>
          </View>
          <View className="trip-title">
            <Text className="t-name">{t.route_name}</Text>
            <Text className="t-region">{t.region}</Text>
          </View>
          <View className={`status-badge${isDone ? ' blue' : ''}`}>{isDone ? '已完成' : '进行中'}</View>
        </View>

        <View className="trip-meta">
          集合 <Text className="hl">{fmtMeet(t.meet_at)}</Text>
          {t.meet_place ? <Text className="hl"> · {t.meet_place}</Text> : null}
        </View>

        <View className="trip-stats">
          <Text>
            ★难度 <Text className="b">{t.difficulty}</Text>
          </Text>
          <Text>
            <Text className="b">{fmtNum(t.distance_km)}</Text> km
          </Text>
          <Text>
            ↑<Text className="b">{t.climb_m}</Text> m
          </Text>
          {t.duration_h !== null ? (
            <Text>
              ≈<Text className="b">{fmtNum(t.duration_h)}</Text>h
            </Text>
          ) : null}
        </View>

        {t.gear_missing.length > 0 ? (
          <View className="trip-gear">
            <View className="g-count">
              <Text className="warn-ico">🎒</Text>装备提醒 {t.gear_missing.length} 条
            </View>
            <View className="g-chips">
              {t.gear_missing.map((key) => (
                <View key={key} className="chip">
                  {gearLabels[key] ?? key}
                </View>
              ))}
            </View>
          </View>
        ) : null}

        <View className="trip-actions">
          {!isDone ? (
            <View
              className={`act act-done${busyId === t.id ? ' is-loading' : ''}`}
              onClick={() => void markDone(t)}
            >
              ✓ 标记完成
            </View>
          ) : null}
          <View
            className={`act act-del${busyId === t.id ? ' is-loading' : ''}`}
            onClick={() => removeTrip(t)}
          >
            🗑 删除
          </View>
        </View>
      </View>
    )
  }

  return (
    <View className="trips-page">
      <View className="trips-title">
        我的<Text className="em">行程</Text>
      </View>
      <View className="trips-sub">
        {counts.planned} 个进行中 · {counts.done} 个足迹
      </View>

      <View className="trips-tabs">
        <View className={`tab-pill${tab === 'planned' ? ' on' : ''}`} onClick={() => switchTab('planned')}>
          进行中 <Text className="cnt">{counts.planned}</Text>
        </View>
        <View className={`tab-pill${tab === 'done' ? ' on' : ''}`} onClick={() => switchTab('done')}>
          足迹 <Text className="cnt">{counts.done}</Text>
        </View>
      </View>

      {loading ? <View className="trips-state">加载中…</View> : null}

      {!loading && error ? (
        <View className="trips-state">
          <View className="st-title">加载失败</View>
          <View className="st-sub">{error}</View>
          <View className="btn btn-ghost" onClick={() => void load()}>
            重试
          </View>
        </View>
      ) : null}

      {!loading && !error && trips.length === 0 ? (
        tab === 'planned' ? (
          <View className="trips-empty">
            <View className="empty-ico">🧭</View>
            <View className="empty-title">还没有行程计划</View>
            <View className="empty-sub">和 AI 聊聊你的下一次出行，聊完一键生成完整计划</View>
            <View className="btn btn-primary empty-btn" onClick={goChat}>
              去 AI 对话生成 →
            </View>
          </View>
        ) : (
          <View className="trips-empty">
            <View className="empty-ico">🐾</View>
            <View className="empty-title">足迹还是空的</View>
            <View className="empty-sub">把「进行中」的行程标记完成后，就会出现在这里</View>
          </View>
        )
      ) : null}

      {!loading && !error && trips.length > 0 ? <View className="trip-list">{trips.map(renderCard)}</View> : null}
    </View>
  )
}
