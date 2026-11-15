#!/usr/bin/env node
/**
 * design tokens 生成器：
 *   读 design/tokens.json → 生成 miniapp/src/styles/tokens.css
 *   （:root + page 两段 :root CSS 变量，:root 供 H5，page 供 weapp）
 *
 * 用法：node design/build-tokens.mjs   （或在 miniapp 下 npm run gen:tokens）
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const tokensPath = resolve(here, 'tokens.json')
const outPath = resolve(here, '../miniapp/src/styles/tokens.css')

// camelCase（含数字后缀）→ kebab-case：bgOuter1 → bg-outer-1，card2 → card-2，accent2 → accent-2
function kebab(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([a-zA-Z])(\d)/g, '$1-$2')
    .toLowerCase()
}

const tokens = JSON.parse(readFileSync(tokensPath, 'utf8'))
const groups = ['color', 'radius', 'spacing', 'typography']

const declarations = []
for (const group of groups) {
  const obj = tokens[group]
  if (!obj || typeof obj !== 'object') {
    throw new Error(`tokens.json 缺少分组 "${group}"`)
  }
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value !== 'string') {
      throw new Error(`tokens.json ${group}.${key} 必须是字符串，实际：${JSON.stringify(value)}`)
    }
    declarations.push(`  --${group}-${kebab(key)}: ${value};`)
  }
}

const css = `/* ============================================================
 * 赶路咯 design tokens（本文件由 design/build-tokens.mjs 自动生成，勿手改）
 * 源头：design/tokens.json（color 值抄自 protype/assets/style.css :root）
 * 生成：node design/build-tokens.mjs
 * ============================================================ */
:root {
${declarations.join('\n')}
}

/* weapp 没有 html/:root 根元素，变量挂在 page 上（Taro 小程序端写法） */
page {
${declarations.join('\n')}
}
`

mkdirSync(dirname(outPath), { recursive: true })
writeFileSync(outPath, css, 'utf8')
console.log(`[build-tokens] ${declarations.length} vars -> ${outPath}`)
