/**
 * M7.5 多型号装备勾选态纯函数回归（selFromRows / payloadFromSel / itemRowCount）：
 * - 同 item 多型号 → 多条 {item_key, model_id}（后端 UNIQUE(item_key,model_id) 允许）
 * - custom_name 自定义一条（model_id=null）；bare 兼容 MVP「只勾 item」老数据
 * - custom 与 bare 同占 (item_key,null)：custom 非空时 bare 不出条目（防 422 重复）
 */
import { describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({ default: {} }))

import { itemRowCount, payloadFromSel, selFromRows, type GearItemOut } from '../src/api/gear'

const row = (item_key: string, model_id: number | null, custom_name: string | null = null): GearItemOut =>
  ({ item_key, model_id, custom_name } as GearItemOut)

describe('selFromRows', () => {
  it('聚合同 item 的多条型号行', () => {
    const sel = selFromRows([row('poles', 1), row('poles', 3), row('pack', 2)])
    expect(sel['poles']).toEqual({ models: [1, 3], custom: '', bare: false })
    expect(sel['pack']).toEqual({ models: [2], custom: '', bare: false })
  })

  it('custom_name 行归 custom；裸行（model_id=null 无名）归 bare；命名空串不算 custom', () => {
    const sel = selFromRows([
      row('shoes', null, '压箱底的旧伙计'),
      row('kit', null, null),
      row('cap', null, '   '),
    ])
    expect(sel['shoes'].custom).toBe('压箱底的旧伙计')
    expect(sel['kit'].bare).toBe(true)
    expect(sel['cap'].custom).toBe('')
    expect(sel['cap'].bare).toBe(true) // 空白 custom 视为裸标记
  })

  it('空清单 → 空勾选态', () => {
    expect(selFromRows([])).toEqual({})
  })
})

describe('payloadFromSel', () => {
  it('多型号展开为多条，同 item 型号 + 自定义并存', () => {
    const payload = payloadFromSel({
      poles: { models: [1, 3], custom: '', bare: false },
      shoes: { models: [7], custom: '旧伙计', bare: false },
    })
    expect(payload).toEqual([
      { item_key: 'poles', model_id: 1 },
      { item_key: 'poles', model_id: 3 },
      { item_key: 'shoes', model_id: 7 },
      { item_key: 'shoes', model_id: null, custom_name: '旧伙计' },
    ])
  })

  it('custom 压掉 bare（同 item 只占一个 (item,null)，防 UNIQUE 422）', () => {
    const payload = payloadFromSel({ kit: { models: [], custom: '自组急救包', bare: true } })
    expect(payload).toEqual([{ item_key: 'kit', model_id: null, custom_name: '自组急救包' }])
  })

  it('bare 且无型号无 custom → 一条裸条目（兼容 MVP 老数据）', () => {
    const payload = payloadFromSel({ cap: { models: [], custom: '', bare: true } })
    expect(payload).toEqual([{ item_key: 'cap', model_id: null, custom_name: null }])
  })

  it('bare 与型号并存时只出型号条目', () => {
    const payload = payloadFromSel({ pack: { models: [5], custom: '', bare: true } })
    expect(payload).toEqual([{ item_key: 'pack', model_id: 5 }])
  })

  it('空勾选态 → 空数组（PUT 清空清单合法）', () => {
    expect(payloadFromSel({})).toEqual([])
  })
})

describe('itemRowCount（计数联动「完成，已带 N 件」）', () => {
  it('与 payload 条数一致', () => {
    const sel = {
      poles: { models: [1, 3], custom: '', bare: false },
      shoes: { models: [7], custom: '旧伙计', bare: false },
      kit: { models: [], custom: '自组急救包', bare: true },
      cap: { models: [], custom: '', bare: true },
      pack: { models: [5], custom: '', bare: true },
    }
    expect(itemRowCount(sel.poles)).toBe(2)
    expect(itemRowCount(sel.shoes)).toBe(2)
    expect(itemRowCount(sel.kit)).toBe(1)
    expect(itemRowCount(sel.cap)).toBe(1)
    expect(itemRowCount(sel.pack)).toBe(1)
    expect(payloadFromSel(sel)).toHaveLength(7)
    expect(itemRowCount(undefined)).toBe(0)
  })
})
