/**
 * 装备清单页（M7 Task 2 落地，M7.5 Task 1 升级为完整多型号版，对齐原型 04）：
 * - GET /gear/catalog（公开）类目 → 装备项 → 型号 三级分组渲染
 * - GET /gear-list 回显 + PUT /gear-list 整体保存；完整版解锁同 item **多型号**
 *   多选：勾 K 个型号 → K 条 {item_key, model_id}（后端 UNIQUE(item_key,model_id)）；
 *   custom_name 自定义一条（model_id=null）；bare 兼容 MVP「只勾 item」老数据
 * - 行点击 = 展开/收起型号面板；型号卡多选；gck 快捷圈 = 一键拥有/取消整项；
 *   计数联动「完成，已带 N 件」→ 成功后 reLaunch 首页（引导流终点）
 * - 未登录降级态（gear-list 需要登录）
 */
import { useCallback, useMemo, useState } from 'react'
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import {
  getCatalog,
  getGearList,
  putGearList,
  payloadFromSel,
  selFromRows,
  itemRowCount,
  type GearCatalog,
  type GearCatalogItem,
  type GearItemSel,
  type GearSelMap,
  type GearModelOut,
} from '@/api/gear'
import { getTokenPair } from '@/api/auth'
import { HOME_PAGE, LOGIN_PAGE, type ApiError } from '@/api/client'
import './index.scss'

type PagePhase = 'checking' | 'guest' | 'ready'

/** 分类 chips 的 emoji（原型 04 gear-cats 同款；'all' = 全部） */
const CAT_EMOJI: Record<string, string> = {
  shoes: '👟',
  tech: '🧊',
  pack: '🎒',
  cloth: '🧥',
  elec: '🔋',
  sun: '🧢',
  camp: '⛺',
  water: '💧',
}

/** 行副标题摘要：型号数 / 自定义名 / 裸标记 */
function itemSummary(sel: GearItemSel | undefined): string {
  if (!sel) return ''
  const parts: string[] = []
  if (sel.models.length) parts.push(`${sel.models.length} 个型号`)
  if (sel.custom) parts.push(sel.custom)
  if (!parts.length && sel.bare) parts.push('已选')
  return parts.join(' · ')
}

export default function Gear() {
  const [phase, setPhase] = useState<PagePhase>('checking')
  const [catalog, setCatalog] = useState<GearCatalog | null>(null)
  const [selection, setSelection] = useState<GearSelMap>({})
  const [activeCat, setActiveCat] = useState<string>('all')
  const [openKey, setOpenKey] = useState<string | null>(null)
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
    // catalog 公开、gear-list 需登录；catalog 失败不阻塞勾选态展示
    const [catRes, listRes] = await Promise.allSettled([getCatalog(), getGearList()])
    if (catRes.status === 'fulfilled') setCatalog(catRes.value)
    if (listRes.status === 'fulfilled') setSelection(selFromRows(listRes.value))
    const failed = [catRes, listRes].find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined
    if (failed) {
      const e = failed.reason as ApiError
      setPageError(e?.detail || String(failed.reason))
    }
    setPhase('ready')
  }, [])

  useDidShow(() => {
    void loadData()
  })

  /* 型号卡多选：勾/取消单个型号（勾选后 bare 被型号条目覆盖，状态上直接清掉） */
  const toggleModel = (key: string, model: GearModelOut): void => {
    setSaveMsg('')
    setSelection((cur) => {
      const item: GearItemSel = cur[key] ?? { models: [], custom: '', bare: false }
      const has = item.models.includes(model.id)
      const models = has ? item.models.filter((m) => m !== model.id) : [...item.models, model.id]
      return { ...cur, [key]: { models, custom: item.custom, bare: has && models.length === 0 ? item.bare : false } }
    })
  }

  /* gck 快捷圈：有勾选（型号/自定义/裸标记任一）→ 整项清空；无勾选 → 裸标记「已拥有」 */
  const toggleOwn = (key: string): void => {
    setSaveMsg('')
    setSelection((cur) => {
      const item = cur[key]
      if (item && itemRowCount(item) > 0) {
        const next = { ...cur }
        delete next[key]
        return next
      }
      return { ...cur, [key]: { models: [], custom: '', bare: true } }
    })
  }

  const renameCustom = (key: string, name: string): void => {
    setSaveMsg('')
    setSelection((cur) => {
      const item: GearItemSel = cur[key] ?? { models: [], custom: '', bare: false }
      return { ...cur, [key]: { ...item, custom: name } }
    })
  }

  /* 完成：PUT 整体覆盖；成功 → reLaunch 首页（引导流终点 / 常规编辑回入口） */
  const finish = async (): Promise<void> => {
    if (saving) return
    setSaving(true)
    setSaveMsg('')
    try {
      await putGearList(payloadFromSel(selection))
      await Taro.reLaunch({ url: HOME_PAGE })
    } catch (err) {
      const e = err as ApiError
      setSaveMsg(`保存失败：${e?.detail || String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  const goLogin = (): void => {
    void Taro.reLaunch({ url: LOGIN_PAGE })
  }

  /* 类目过滤 + 按类目分组（保持 catalog 返回顺序） */
  const visibleItems = useMemo<GearCatalogItem[]>(() => {
    if (!catalog) return []
    return catalog.items.filter((it) => activeCat === 'all' || it.category === activeCat)
  }, [catalog, activeCat])

  const grouped = useMemo<{ key: string; label: string; items: GearCatalogItem[] }[]>(() => {
    if (!catalog) return []
    return catalog.categories
      .map((c) => ({ key: c.key, label: c.label, items: visibleItems.filter((it) => it.category === c.key) }))
      .filter((g) => g.items.length > 0)
  }, [catalog, visibleItems])

  /* 计数联动：与 PUT payload 条数严格一致（型号条 + 自定义条 + 裸标记条） */
  const total = useMemo(
    () => Object.values(selection).reduce((acc, s) => acc + itemRowCount(s), 0),
    [selection],
  )
  const catCount = (catKey: string): number =>
    catalog?.items
      .filter((it) => it.category === catKey)
      .reduce((acc, it) => acc + itemRowCount(selection[it.key]), 0) ?? 0

  /* ---------- 未登录 / 加载态 ---------- */
  if (phase !== 'ready') {
    return (
      <View className="gear-page">
        <View className="guest-card">
          <View className="guest-avatar">🎒</View>
          <View className="guest-title">{phase === 'checking' ? '加载中…' : '还未登录'}</View>
          <View className="guest-sub">
            {phase === 'checking'
              ? '正在拉取装备目录与你的清单'
              : '登录后同步你的装备清单（装备将参与路线安全匹配）'}
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
    <View className="gear-page">
      <View className="gear-title">
        挑选你的<Text className="em">徒步装备</Text>
      </View>
      <View className="gear-sub">
        点开装备，从常见品牌/型号中快速勾选（可多选），也可填自定义名称。装备将参与路线安全匹配。已带{' '}
        <Text className="hl">{total}</Text> 件。
      </View>

      {pageError && (
        <View className="gear-error">
          <Text>{pageError}</Text>
        </View>
      )}

      {/* 分类筛选 chips（全部 + 8 类，横向滚动） */}
      <View className="gear-cats">
        <View
          className={`chip${activeCat === 'all' ? ' on' : ''}`}
          onClick={() => setActiveCat('all')}
        >
          全部
        </View>
        {(catalog?.categories ?? []).map((c) => (
          <View
            key={c.key}
            className={`chip${activeCat === c.key ? ' on' : ''}`}
            onClick={() => setActiveCat(c.key)}
          >
            {CAT_EMOJI[c.key] || ''} {c.label}
          </View>
        ))}
      </View>

      {/* 分组渲染：类目 → 装备项（行点击展开型号面板；型号卡多选；gck 一键拥有/取消） */}
      {grouped.map((g) => (
        <View key={g.key}>
          <View className="gear-cat-head">
            <Text className="gear-cat-title">{CAT_EMOJI[g.key] || ''} {g.label}</Text>
            <Text className="gear-cat-count">{catCount(g.key)} 件</Text>
          </View>
          {g.items.map((it) => {
            const sel = selection[it.key]
            const selCount = itemRowCount(sel)
            const open = openKey === it.key
            return (
              <View key={it.key} className={`gear-item${selCount > 0 ? ' sel' : ''}${open ? ' open' : ''}`}>
                <View className="gear-row" onClick={() => setOpenKey(open ? null : it.key)}>
                  <View className="gic">{CAT_EMOJI[it.category] || '🧰'}</View>
                  <View className="gt">
                    <Text className="gt-name">{it.label}</Text>
                    <Text className="gt-sub">
                      {selCount > 0 ? itemSummary(sel) || '已选' : `含 ${it.models.length} 个常见型号`}
                    </Text>
                  </View>
                  <View className="gck" onClick={(e) => {
                    e.stopPropagation()
                    toggleOwn(it.key)
                  }}>✓</View>
                </View>
                {open && (
                  <View className="gsub">
                    {it.models.length > 0 && (
                      <View className="mgrid">
                        {it.models.map((m) => {
                          const mSel = !!sel?.models.includes(m.id)
                          return (
                            <View
                              key={m.id}
                              className={`model${mSel ? ' sel' : ''}`}
                              onClick={() => toggleModel(it.key, m)}
                            >
                              <Text className="m-brand">{m.brand}</Text>
                              <Text className="m-name">{m.model}</Text>
                              <Text className="m-spec">{m.spec}</Text>
                              <View className="tick">✓</View>
                            </View>
                          )
                        })}
                      </View>
                    )}
                    <View className="cname-box">
                      <Text className="cname-label">自定义名称（与型号可并存，各算一件）</Text>
                      <Input
                        className="cname-input"
                        type="text"
                        placeholder="如：压箱底的旧伙计"
                        placeholderClass="field-placeholder"
                        value={sel?.custom ?? ''}
                        onInput={(e) => renameCustom(it.key, e.detail.value)}
                      />
                    </View>
                  </View>
                )}
              </View>
            )
          })}
        </View>
      ))}

      {/* 完成：PUT /gear-list → reLaunch 首页（计数与 payload 条数联动） */}
      <View
        className={`btn btn-primary save-bar${saving ? ' is-loading' : ''}`}
        onClick={() => void finish()}
      >
        {saving ? '保存中…' : `完成，已带 ${total} 件`}
      </View>
      {saveMsg && <View className="save-msg">{saveMsg}</View>}
    </View>
  )
}
