/**
 * 装备清单页（M7 Task 2，对齐原型 04-onboard-gear 简化版）：
 * - GET /gear/catalog（公开）类目 → 装备项 → 型号 三级分组渲染
 * - GET /gear-list 勾选态 + PUT /gear-list 整体保存（item_key / model_id / custom_name）
 * - 分类筛选 chips（全部 + 8 类）；项内型号选择（MVP 简化：每个 item 至多一条，
 *   model_id 可选 + custom_name 可填；后端按 (item_key, model_id) 查重）
 * - 未登录降级态（gear-list 需要登录）
 */
import { useCallback, useMemo, useState } from 'react'
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import {
  getCatalog,
  getGearList,
  putGearList,
  type GearCatalog,
  type GearCatalogItem,
  type GearModelOut,
} from '@/api/gear'
import { getTokenPair } from '@/api/auth'
import { LOGIN_PAGE, type ApiError } from '@/api/client'
import './index.scss'

type PagePhase = 'checking' | 'guest' | 'ready'

/** 本地勾选态：item_key → 型号/自定义名（与后端 GearItemIn 一一对应） */
type Selection = Record<string, { model_id: number | null; custom_name: string | null }>

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

export default function Gear() {
  const [phase, setPhase] = useState<PagePhase>('checking')
  const [catalog, setCatalog] = useState<GearCatalog | null>(null)
  const [selection, setSelection] = useState<Selection>({})
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
    if (listRes.status === 'fulfilled') {
      const next: Selection = {}
      for (const it of listRes.value) {
        next[it.item_key] = { model_id: it.model_id, custom_name: it.custom_name }
      }
      setSelection(next)
    }
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

  const toggleItem = (key: string): void => {
    setSaveMsg('')
    setSelection((cur) => {
      const next = { ...cur }
      if (next[key]) {
        delete next[key]
      } else {
        next[key] = { model_id: null, custom_name: null }
      }
      return next
    })
  }

  const pickModel = (key: string, model: GearModelOut): void => {
    setSaveMsg('')
    setSelection((cur) => {
      const curItem = cur[key]
      if (!curItem) return cur
      return {
        ...cur,
        [key]: { ...curItem, model_id: curItem.model_id === model.id ? null : model.id },
      }
    })
  }

  const renameCustom = (key: string, name: string): void => {
    setSelection((cur) => (cur[key] ? { ...cur, [key]: { ...cur[key], custom_name: name } } : cur))
  }

  const save = async (): Promise<void> => {
    if (saving) return
    setSaving(true)
    setSaveMsg('')
    try {
      const items = Object.entries(selection).map(([item_key, v]) => ({
        item_key,
        model_id: v.model_id,
        custom_name: v.custom_name && v.custom_name.trim() ? v.custom_name.trim() : null,
      }))
      const saved = await putGearList(items)
      const next: Selection = {}
      for (const it of saved) {
        next[it.item_key] = { model_id: it.model_id, custom_name: it.custom_name }
      }
      setSelection(next)
      setSaveMsg(`已保存 ${saved.length} 件装备`)
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

  const total = Object.keys(selection).length
  const itemCount = (key: string): string => {
    const it = selection[key]
    if (!it) return ''
    const model = catalog?.items.find((x) => x.key === key)?.models.find((m) => m.id === it.model_id)
    return model ? `${model.brand} ${model.model}` : it.custom_name || '已选'
  }

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
        点开装备选择常见品牌/型号，也可填自定义名称。已带 <Text className="hl">{total}</Text> 件。
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

      {/* 分组渲染：类目 → 装备项（展开显示型号网格 + 自定义名） */}
      {grouped.map((g) => (
        <View key={g.key}>
          <View className="gear-cat-head">
            <Text className="gear-cat-title">{CAT_EMOJI[g.key] || ''} {g.label}</Text>
            <Text className="gear-cat-count">{g.items.filter((it) => selection[it.key]).length} 件</Text>
          </View>
          {g.items.map((it) => {
            const sel = !!selection[it.key]
            const open = openKey === it.key
            return (
              <View key={it.key} className={`gear-item${sel ? ' sel' : ''}${open ? ' open' : ''}`}>
                <View
                  className="gear-row"
                  onClick={() => {
                    setOpenKey(open ? null : it.key)
                    if (!sel) toggleItem(it.key)
                  }}
                >
                  <View className="gic">{CAT_EMOJI[it.category] || '🧰'}</View>
                  <View className="gt">
                    <Text className="gt-name">{it.label}</Text>
                    <Text className="gt-sub">{sel ? itemCount(it.key) || '已选' : `含 ${it.models.length} 个常见型号`}</Text>
                  </View>
                  <View className="gck">✓</View>
                </View>
                {open && (
                  <View className="gsub">
                    {it.models.length > 0 && (
                      <View className="mgrid">
                        {it.models.map((m) => {
                          const mSel = selection[it.key]?.model_id === m.id
                          return (
                            <View
                              key={m.id}
                              className={`model${mSel ? ' sel' : ''}`}
                              onClick={() => pickModel(it.key, m)}
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
                      <Text className="cname-label">自定义名称</Text>
                      <Input
                        className="cname-input"
                        type="text"
                        placeholder="如：压箱底的旧伙计"
                        placeholderClass="field-placeholder"
                        value={selection[it.key]?.custom_name ?? ''}
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

      {/* 保存（整体 PUT /gear-list） */}
      <View
        className={`btn btn-primary save-bar${saving ? ' is-loading' : ''}`}
        onClick={save}
      >
        {saving ? '保存中…' : `保存清单（${total} 件）`}
      </View>
      {saveMsg && <View className="save-msg">{saveMsg}</View>}
    </View>
  )
}
