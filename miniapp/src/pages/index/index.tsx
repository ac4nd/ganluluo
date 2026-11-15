import { useCallback, useState } from 'react'
import { Button, Text, View } from '@tarojs/components'

import { health, type ApiError } from '@/api/client'
import './index.scss'

type ProbeState =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'ok'; text: string }
  | { state: 'fail'; text: string }

/** M7 Task 1 占位页：验证脚手架 + tokens + 类型化 API 层跑通 */
export default function Index() {
  const [probe, setProbe] = useState<ProbeState>({ state: 'idle' })

  // 调 GET /ops/health（dev 走 devServer 同源代理 → 本地 uvicorn 8123）
  const testBackend = useCallback(async () => {
    setProbe({ state: 'loading' })
    try {
      const data = await health()
      setProbe({ state: 'ok', text: `/ops/health 200 → ${JSON.stringify(data)}` })
    } catch (err) {
      const e = err as ApiError
      setProbe({ state: 'fail', text: `失败 status=${e?.status ?? '?'} detail=${e?.detail ?? String(err)}` })
    }
  }, [])

  return (
    <View className="index-page">
      <View className="hero-card">
        <View className="hero-label">GANLULUO · M7 轻端</View>
        <View className="hero-title">
          赶路咯 <Text className="em">轻端地基 OK</Text>
        </View>
        <View className="hero-sub">
          Taro 4 + React 18 + TS + webpack5；design tokens 已接入
          （design/tokens.json → src/styles/tokens.css）；类型化 API 层已就绪
          （src/api/*）。
        </View>
      </View>

      <View className="panel">
        <View className="panel-title">后端连通性</View>
        <Button
          className={`probe-btn${probe.state === 'loading' ? ' is-loading' : ''}`}
          loading={probe.state === 'loading'}
          onClick={testBackend}
        >
          测试后端连接
        </Button>
        {probe.state !== 'idle' && probe.state !== 'loading' && (
          <View className={`probe-result ${probe.state}`}>
            <Text>{probe.text}</Text>
          </View>
        )}
        <View className="probe-hint">
          dev 环境走 Taro devServer 同源代理 → 本地 uvicorn（127.0.0.1:8123）；
          GL_API_BASE 可在构建期覆盖（weapp 真机必填局域网地址）。
        </View>
      </View>
    </View>
  )
}
