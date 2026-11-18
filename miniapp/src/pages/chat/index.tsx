/**
 * AI 对话页（M7 Task 4，对齐原型 06-ai-plan-chat.html）：
 * - POST /assistant/chat SSE 流（client.ts sse()：H5 fetch / weapp enableChunked 双端流式，data: 行 JSON 事件）
 *   事件协议 {type: session|token|clarify|cards|sources|quota_exceeded|done, data}：
 *   token 增量累积到当前 ai 气泡；clarify → 问题气泡 + options chips（点选即作为用户消息发送）；
 *   cards → 路线缩略卡（跳 route-detail?id=N）；sources → 可折叠「引用来源」；
 *   quota_exceeded → 提示卡 + 「生成完整计划」置灰
 * - 输入区：input + 配额环按钮（GET /assistant/quota；原型 06 hover 明细在小程序改为
 *   点击弹出半屏明细：两进度条 + 档位徽章 + 重置时间）+ 发送（流式中变停止 = abort）
 * - 「生成完整计划」→ POST /assistant/plan({session_id}) → 200 跳 /pages/trips + toast；
 *   422/404 在 plan 条下方显示 detail
 * - 401：sse() 无自动续期（chat 为登录态必需端点，审查备忘接受该行为）→ onError 提示重登并跳登录页
 * - M8 Task 4 游客模式：入口即拦（FAB/tab requireAuth 弹「登录后可用」）；页内防御保留
 *   （游客深链直入 → 登录提示卡 + 900ms 兜底跳登录），发送 / 生成计划前再统一 requireAuth()
 * - 发送中禁重复提交；useDidHide / 卸载时 abort
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'

import { chat, generatePlan, quota, type UsageOut } from '@/api/assistant'
import { getTokenPair, HOME_PAGE, LOGIN_PAGE, type ApiError, type SseEvent, type SseHandle } from '@/api/client'
import { requireAuth } from '@/api/guard'
import { SPORTS } from '@/api/profile'
import './index.scss'

const TRIPS_PAGE = '/pages/trips/index'
const DETAIL_PAGE = '/pages/route-detail/index'
const PROFILE_PAGE = '/pages/profile/index'

/** 配额环三级色阈值（对齐原型：≥60 warn 琥珀 / ≥85 danger 红） */
const WARN_PCT = 60
const DANGER_PCT = 85

/** 卡片缩略图渐变（对齐 routes 页 SPORT_THUMB 口径） */
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

/** chat 事件 cards 的路线缩略卡（tools.search_routes_for 产出，字段做窄型兜底） */
interface MiniCard {
  id: number
  name: string
  region: string
  sport: string
  difficulty: number
  distance_km: number
  climb_m: number
  duration_h: number | null
  match: number | null
}

/** sources 事件引用项（session knowledge 检索产出） */
interface SourceItem {
  source_name: string
  chunk_no: number
}

type Msg =
  | { kind: 'user'; id: number; text: string }
  | { kind: 'ai'; id: number; text: string; streaming: boolean }
  | { kind: 'clarify'; id: number; question: string; options: string[]; answered: boolean }
  | { kind: 'cards'; id: number; items: MiniCard[] }
  | { kind: 'sources'; id: number; items: SourceItem[]; open: boolean }
  | { kind: 'quota'; id: number; tier: string; used: number; limit: number; resetAt: string }
  | { kind: 'error'; id: number; text: string }

const GREETING =
  '嗨，我是赶路咯 AI 规划师 🥾 想去哪儿、做什么运动，直接跟我说；我会帮你查成熟路线、看里程爬升，聊完可以一键生成完整行程计划。'

const sportLabel = (key: string): string => SPORTS.find((s) => s.key === key)?.label ?? key
const sportEmoji = (key: string): string => SPORTS.find((s) => s.key === key)?.emoji ?? '🥾'
const fmtNum = (v: number | null | undefined): string =>
  v === null || v === undefined ? '—' : v.toFixed(1).replace(/\.0$/, '')
/** token 用量缩写（对齐原型 fmt：≥10000 → k） */
const fmtTokens = (n: number): string =>
  n >= 10000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : String(n)
const tierLabel = (tier: string): string => (tier === 'vip' ? 'VIP 会员' : '试用版')

/** cards 事件数据窄型化：非数组/缺字段兜底，避免后端 loose dict 直接进渲染层 */
function asCards(data: unknown): MiniCard[] {
  if (!Array.isArray(data)) return []
  return data
    .filter((x): x is Record<string, unknown> => x !== null && typeof x === 'object')
    .map((x) => ({
      id: Number(x.id),
      name: String(x.name ?? '未命名路线'),
      region: String(x.region ?? ''),
      sport: String(x.sport ?? 'hiking'),
      difficulty: Number(x.difficulty ?? 0),
      distance_km: Number(x.distance_km ?? 0),
      climb_m: Number(x.climb_m ?? 0),
      duration_h: x.duration_h === null || x.duration_h === undefined ? null : Number(x.duration_h),
      match: typeof x.match === 'number' ? x.match : null,
    }))
    .filter((c) => Number.isFinite(c.id))
}

function asSources(data: unknown): SourceItem[] {
  if (!Array.isArray(data)) return []
  return data
    .filter((x): x is Record<string, unknown> => x !== null && typeof x === 'object')
    .map((x) => ({
      source_name: String(x.source_name ?? ''),
      chunk_no: Number(x.chunk_no ?? 0),
    }))
}

/** 当前流式中的 ai 气泡置为完成（token 阶段结束/收到其它事件时） */
function markAiDone(list: Msg[]): Msg[] {
  const last = list[list.length - 1]
  if (last && last.kind === 'ai' && last.streaming) {
    return [...list.slice(0, -1), { ...last, streaming: false }]
  }
  return list
}

/** 路线缩略卡（对齐原型 .route-mini：山景缩略 + 名称 + tags + meta） */
function MiniRouteCard({ card, onOpen }: { card: MiniCard; onOpen: () => void }) {
  const [c1, c2] = SPORT_THUMB[card.sport] ?? ['#41603a', '#0b140b']
  const gid = `mc-grad-${card.id}`
  return (
    <View className="mini-card" onClick={onOpen}>
      <svg className="mthumb" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={c1} />
            <stop offset="1" stopColor={c2} />
          </linearGradient>
        </defs>
        <rect width="100" height="100" fill={`url(#${gid})`} />
        <circle cx="72" cy="26" r="13" fill="#f2dd7d" opacity=".9" />
        <path d="M0 62l30-20 26 14 22-16 22 16v44H0z" fill="#17311c" opacity=".85" />
        <path d="M0 80l28-16 26 12 24-14 22 10v28H0z" fill="#0c1c10" />
      </svg>
      <View className="minfo">
        <Text className="mname">{card.name}</Text>
        <View className="mtags">
          <View className="tag">
            {sportEmoji(card.sport)} {sportLabel(card.sport)}
          </View>
          <View className="tag">★难度 {card.difficulty}</View>
          {card.match !== null ? <View className="tag blue">匹配 {card.match}%</View> : null}
        </View>
        <View className="mmeta">
          <Text>
            <Text className="b">{fmtNum(card.distance_km)}</Text> km
          </Text>
          <Text>
            ↑<Text className="b">{card.climb_m}</Text> m
          </Text>
          <Text>
            ≈<Text className="b">{fmtNum(card.duration_h)}</Text>h
          </Text>
        </View>
      </View>
    </View>
  )
}

export default function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([{ kind: 'ai', id: 0, text: GREETING, streaming: false }])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [planErr, setPlanErr] = useState('')
  const [hasSession, setHasSession] = useState(false)
  const [quotaInfo, setQuotaInfo] = useState<UsageOut | null>(null)
  const [quotaExceeded, setQuotaExceeded] = useState(false)
  const [quotaOpen, setQuotaOpen] = useState(false)
  const [authed] = useState<boolean>(() => getTokenPair() !== null)

  const idRef = useRef(1)
  const nid = (): number => idRef.current++
  const sessionRef = useRef<string | null>(null)
  const handleRef = useRef<SseHandle | null>(null)

  /* ---------- 配额 ---------- */
  const refreshQuota = useCallback(async (): Promise<void> => {
    if (!getTokenPair()) return
    try {
      const q = await quota()
      setQuotaInfo(q)
      // 后端 allowed = 用量 < 限额：初始就是超额态也直接置灰计划按钮
      setQuotaExceeded(!q.allowed)
    } catch {
      /* 配额拉取失败不打断对话；环显示 --% */
    }
  }, [])

  useDidShow(() => {
    void refreshQuota()
  })

  /* ---------- SSE 事件 → 消息流 ---------- */
  const onEvent = useCallback(
    (e: SseEvent): void => {
      const type = typeof e.type === 'string' ? e.type : ''
      const data = e.data as unknown
      switch (type) {
        case 'session': {
          sessionRef.current = String(data)
          setHasSession(true)
          break
        }
        case 'token': {
          const piece = String(data ?? '')
          if (!piece) break
          setMsgs((prev) => {
            const last = prev[prev.length - 1]
            if (last && last.kind === 'ai' && last.streaming) {
              return [...prev.slice(0, -1), { ...last, text: last.text + piece }]
            }
            return [...prev, { kind: 'ai', id: nid(), text: piece, streaming: true }]
          })
          break
        }
        case 'clarify': {
          const d = (data ?? {}) as Record<string, unknown>
          setMsgs((prev) => [
            ...markAiDone(prev),
            {
              kind: 'clarify',
              id: nid(),
              question: String(d.question ?? ''),
              options: Array.isArray(d.options) ? d.options.map(String) : [],
              answered: false,
            },
          ])
          break
        }
        case 'cards': {
          setMsgs((prev) => [...markAiDone(prev), { kind: 'cards', id: nid(), items: asCards(data) }])
          break
        }
        case 'sources': {
          setMsgs((prev) => [
            ...markAiDone(prev),
            { kind: 'sources', id: nid(), items: asSources(data), open: false },
          ])
          break
        }
        case 'quota_exceeded': {
          const d = (data ?? {}) as Record<string, unknown>
          setQuotaExceeded(true)
          setMsgs((prev) => [
            ...markAiDone(prev),
            {
              kind: 'quota',
              id: nid(),
              tier: String(d.tier ?? ''),
              used: Number(d.daily_chats_used ?? 0),
              limit: Number(d.daily_chats_limit ?? 0),
              resetAt: String(d.reset_at ?? '明日 00:00'),
            },
          ])
          break
        }
        case 'done': {
          setMsgs((prev) => markAiDone(prev))
          setStreaming(false)
          // 一轮对话消耗一次配额：done 后刷新环
          void refreshQuota()
          break
        }
        default:
          break
      }
    },
    [refreshQuota],
  )

  /* ---------- 发送 ---------- */
  const send = useCallback(
    (raw: string): void => {
      const text = raw.trim()
      if (!text || streaming) return
      // M8 Task 4：页级防御（游客深链直入时入口已被 FAB/tab requireAuth 拦下，
      // 这里兜底）；统一弹「登录后可用」，不再静默 reLaunch 登录页
      if (!requireAuth()) return
      setInput('')
      setPlanErr('')
      setMsgs((prev) => [...markAiDone(prev), { kind: 'user', id: nid(), text }])
      setStreaming(true)
      try {
        handleRef.current?.abort()
        handleRef.current = chat(
          { session_id: sessionRef.current, message: text },
          onEvent,
          {
            onError: (err: ApiError) => {
              setStreaming(false)
              setMsgs((prev) => [
                ...markAiDone(prev),
                {
                  kind: 'error',
                  id: nid(),
                  text:
                    err.status === 401
                      ? '登录已过期，请重新登录'
                      : `发送失败：${err.detail || '网络错误'}`,
                },
              ])
              if (err.status === 401) {
                // sse() 不做流式刷新（审查备忘接受）：提示后统一去登录页
                setTimeout(() => {
                  void Taro.reLaunch({ url: LOGIN_PAGE })
                }, 1200)
              }
            },
          },
        )
      } catch (err) {
        // sse() 同步抛错兜底（如同源校验失败）；流内失败走 onError
        setStreaming(false)
        const msg = (err as { message?: string }).message ?? '当前端暂不支持流式对话'
        void Taro.showToast({ title: msg, icon: 'none' })
      }
    },
    [onEvent, streaming],
  )

  /** clarify chip 点选：标记已答 + 选项文本作为用户消息发送 */
  const answerClarify = (msgId: number, option: string): void => {
    setMsgs((prev) =>
      prev.map((m) => (m.kind === 'clarify' && m.id === msgId ? { ...m, answered: true } : m)),
    )
    send(option)
  }

  const toggleSources = (msgId: number): void => {
    setMsgs((prev) =>
      prev.map((m) => (m.kind === 'sources' && m.id === msgId ? { ...m, open: !m.open } : m)),
    )
  }

  /* ---------- 生成完整计划 ---------- */
  const doPlan = async (): Promise<void> => {
    if (planning) return
    // M8 Task 4：游客统一拦截（弹「登录后可用」），原动作不执行
    if (!requireAuth()) return
    if (quotaExceeded) {
      void Taro.showToast({ title: '今日 AI 额度已用尽', icon: 'none' })
      return
    }
    if (!sessionRef.current) {
      void Taro.showToast({ title: '先和 AI 聊聊你的出行想法', icon: 'none' })
      return
    }
    setPlanning(true)
    setPlanErr('')
    try {
      await generatePlan({ session_id: sessionRef.current })
      void Taro.showToast({ title: '计划已生成', icon: 'success', duration: 1500 })
      setTimeout(() => {
        void Taro.navigateTo({ url: TRIPS_PAGE }).catch(() => undefined)
      }, 1200)
    } catch (err) {
      const e = err as ApiError
      setPlanErr(e?.detail || String(err))
    } finally {
      setPlanning(false)
    }
  }

  /* ---------- 离开页面 abort + 流式时滚到底 ---------- */
  useDidHide(() => {
    handleRef.current?.abort()
    setStreaming(false)
    setMsgs((prev) => markAiDone(prev))
  })

  useEffect(() => {
    return () => {
      handleRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!authed) {
      const t = setTimeout(() => {
        void Taro.reLaunch({ url: LOGIN_PAGE })
      }, 900)
      return () => clearTimeout(t)
    }
  }, [authed])

  useEffect(() => {
    const t = setTimeout(() => {
      void Taro.pageScrollTo({ scrollTop: 999999, duration: 0 }).catch(() => undefined)
    }, 40)
    return () => clearTimeout(t)
  }, [msgs])

  /* ---------- 配额环数据 ---------- */
  const pct = quotaInfo
    ? Math.max(
        Math.round((quotaInfo.chats_used / Math.max(1, quotaInfo.daily_chats_limit)) * 100),
        Math.round((quotaInfo.tokens_used / Math.max(1, quotaInfo.daily_tokens_limit)) * 100),
      )
    : 0
  const ringCls =
    quotaInfo && pct >= DANGER_PCT ? ' danger' : quotaInfo && pct >= WARN_PCT ? ' warn' : ''

  const barCls = (used: number, limit: number): string => {
    const p = limit > 0 ? used / limit : 0
    return p >= DANGER_PCT / 100 ? ' danger' : p >= WARN_PCT / 100 ? ' warn' : ''
  }

  /* ---------- 渲染 ---------- */
  const goBack = (): void => {
    void Taro.navigateBack().catch(() => void Taro.reLaunch({ url: HOME_PAGE }))
  }

  if (!authed) {
    return (
      <View className="chat-page">
        <View className="chat-state">
          <View className="cs-ico">🔐</View>
          <View className="cs-title">AI 对话需要登录</View>
          <View className="cs-sub">正在跳转登录页…</View>
        </View>
      </View>
    )
  }

  const renderMsg = (m: Msg): JSX.Element => {
    switch (m.kind) {
      case 'user':
        return (
          <View key={m.id} className="row user">
            <View className="bubble user">{m.text}</View>
          </View>
        )
      case 'ai':
        return (
          <View key={m.id} className="row ai">
            <View className="bubble ai">
              {m.text}
              {m.streaming ? <Text className="cursor">▍</Text> : null}
            </View>
          </View>
        )
      case 'clarify':
        return (
          <View key={m.id} className="row ai">
            <View className="bubble ai">{m.question}</View>
          </View>
        )
      case 'cards':
        return (
          <View key={m.id} className="card-stack">
            {m.items.map((c) => (
              <MiniRouteCard
                key={c.id}
                card={c}
                onOpen={() => {
                  void Taro.navigateTo({ url: `${DETAIL_PAGE}?id=${c.id}` }).catch(() => undefined)
                }}
              />
            ))}
          </View>
        )
      case 'sources':
        return (
          <View key={m.id} className="src-box">
            <View className="src-head" onClick={() => toggleSources(m.id)}>
              📄 引用来源 · {m.items.length} 条
              <Text className="arr">{m.open ? '▾' : '▸'}</Text>
            </View>
            {m.open
              ? m.items.map((s, i) => (
                  <View key={i} className="src-item">
                    {s.source_name}
                    {s.chunk_no > 0 ? ` · 第 ${s.chunk_no} 段` : ''}
                  </View>
                ))
              : null}
          </View>
        )
      case 'quota':
        return (
          <View key={m.id} className="quota-card-evt">
            <View className="qc-evt-title">今日 AI 额度已用尽</View>
            <View className="qc-evt-sub">
              {tierLabel(m.tier)} · 对话 {m.used}/{m.limit} 次 · {m.resetAt}重置
            </View>
          </View>
        )
      case 'error':
        return (
          <View key={m.id} className="row ai">
            <View className="bubble err">{m.text}</View>
          </View>
        )
      default:
        return null
    }
  }

  // clarify 事件的问题与选项合渲染：问题气泡 + chips 同组
  const renderList = (): JSX.Element[] => {
    const out: JSX.Element[] = []
    for (const m of msgs) {
      out.push(renderMsg(m))
      if (m.kind === 'clarify') {
        out.push(
          <View key={`opts-${m.id}`} className="chip-row">
            {m.options.map((op) => (
              <View
                key={op}
                className={`chip opt${m.answered ? ' off' : ''}`}
                onClick={() => {
                  if (!m.answered && !streaming) answerClarify(m.id, op)
                }}
              >
                {op}
              </View>
            ))}
          </View>,
        )
      }
    }
    return out
  }

  return (
    <View className="chat-page">
      {/* M3 顶栏（大标题形态 + 返回圆钮；H5 无原生返回键，weapp 与原生导航并存——同引导页模式） */}
      <View className="chat-top">
        <View className="icon-btn" onClick={goBack}>
          ‹
        </View>
        <View className="chat-top-text">
          <View className="chat-title">AI 规划</View>
          <View className="chat-sub">流式问答 · 聊完一键生成计划</View>
        </View>
      </View>

      <View className="chat-list">{renderList()}</View>

      {/* 底部 dock：生成计划条 + 输入行 */}
      <View className="chat-dock">
        <View className="plan-bar">
          <View
            className={`plan-btn${quotaExceeded || !hasSession ? ' off' : ''}${planning ? ' is-loading' : ''}`}
            onClick={() => void doPlan()}
          >
            <Text>⚡ {planning ? '生成中…' : '生成完整计划'}</Text>
          </View>
        </View>
        {planErr ? <View className="plan-err">生成失败：{planErr}</View> : null}

        <View className="input-row">
          <Input
            className="chat-input"
            type="text"
            value={input}
            placeholder={streaming ? '正在回复中…' : '想去哪类地方？直接说～'}
            placeholderClass="chat-placeholder"
            confirmType="send"
            onInput={(e) => setInput(e.detail.value)}
            onConfirm={() => send(input)}
          />
          {/* 配额环按钮：点击弹半屏明细（原型 06 hover 的触屏替代） */}
          <View
            className={`quota-ring${ringCls}`}
            onClick={() => setQuotaOpen(true)}
            aria-label="今日 AI 额度"
          >
            <svg className="ring" viewBox="0 0 38 38" aria-hidden="true">
              <circle className="arc-bg" cx="19" cy="19" r="16.5" pathLength={100} />
              <circle
                className="arc"
                cx="19"
                cy="19"
                r="16.5"
                pathLength={100}
                strokeDasharray="100"
                strokeDashoffset={100 - pct}
              />
            </svg>
            <View className="ring-v">
              <Text className="qv">{quotaInfo ? `${pct}%` : '--%'}</Text>
              <Text className="qk">已用</Text>
            </View>
          </View>
          {/* 发送 / 停止（流式中 abort） */}
          <View
            className={`send-btn${streaming ? ' stop' : ''}`}
            onClick={() => {
              if (streaming) {
                handleRef.current?.abort()
                setStreaming(false)
                setMsgs((prev) => markAiDone(prev))
              } else {
                send(input)
              }
            }}
            aria-label={streaming ? '停止生成' : '发送'}
          >
            {streaming ? (
              <Text style={{ fontSize: '26px' }}>■</Text>
            ) : (
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
                <path d="M21 3L10 14M21 3l-7 18-4-8-8-4z" />
              </svg>
            )}
          </View>
        </View>
      </View>

      {/* 配额半屏明细 */}
      {quotaOpen ? (
        <View className="sheet-mask" onClick={() => setQuotaOpen(false)}>
          <View className="sheet" onClick={(e) => e.stopPropagation()}>
            <View className="qt-head">
              <Text className="qt-title">今日 AI 额度</Text>
              <View className={`badge-tier ${quotaInfo?.tier === 'vip' ? 'vip' : 'trial'}`}>
                {tierLabel(quotaInfo?.tier ?? 'trial')}
              </View>
            </View>

            <View className="qt-row">
              <Text>对话次数</Text>
              <Text className="qt-val">
                {quotaInfo ? `${quotaInfo.chats_used} / ${quotaInfo.daily_chats_limit} 次` : '- / -'}
              </Text>
            </View>
            <View className={`qt-bar${barCls(quotaInfo?.chats_used ?? 0, quotaInfo?.daily_chats_limit ?? 0)}`}>
              <View
                className="qt-fill"
                style={{
                  width: `${
                    quotaInfo
                      ? Math.min(
                          100,
                          Math.round((quotaInfo.chats_used / Math.max(1, quotaInfo.daily_chats_limit)) * 100),
                        )
                      : 0
                  }%`,
                }}
              />
            </View>

            <View className="qt-row">
              <Text>Token 消耗</Text>
              <Text className="qt-val">
                {quotaInfo
                  ? `${fmtTokens(quotaInfo.tokens_used)} / ${fmtTokens(quotaInfo.daily_tokens_limit)}`
                  : '- / -'}
              </Text>
            </View>
            <View className={`qt-bar${barCls(quotaInfo?.tokens_used ?? 0, quotaInfo?.daily_tokens_limit ?? 0)}`}>
              <View
                className="qt-fill"
                style={{
                  width: `${
                    quotaInfo
                      ? Math.min(
                          100,
                          Math.round((quotaInfo.tokens_used / Math.max(1, quotaInfo.daily_tokens_limit)) * 100),
                        )
                      : 0
                  }%`,
                }}
              />
            </View>

            <View className="qt-foot">
              <Text className="qt-reset">重置：明日 00:00</Text>
              {quotaInfo?.tier !== 'vip' ? (
                <Text
                  className="qt-up"
                  onClick={() => {
                    setQuotaOpen(false)
                    void Taro.navigateTo({ url: PROFILE_PAGE }).catch(() => undefined)
                  }}
                >
                  升级 VIP →
                </Text>
              ) : null}
            </View>

            <View className="sheet-close" onClick={() => setQuotaOpen(false)}>
              关闭
            </View>
          </View>
        </View>
      ) : null}
    </View>
  )
}
