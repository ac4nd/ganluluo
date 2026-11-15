/**
 * 登录页（M7 Task 2）：
 * - 同页双 tab：登录（邮箱+密码）/ 注册（邮箱+昵称+密码，成功后自动 login）
 * - POST /auth/login → setTokenPair（api/auth.login 内已写 storage）→ reLaunch 首页入口
 * - 错误统一展示 normalizeError 的 detail；提交中 loading 禁重复
 * - 已登录访问本页 → 直接 reLaunch 回首页入口（简易守卫）
 */
import { useEffect, useState } from 'react'
import { Input, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import { login, register, getTokenPair } from '@/api/auth'
import { HOME_PAGE, type ApiError } from '@/api/client'
import './index.scss'

type Mode = 'login' | 'register'

export default function Login() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // 简易路由守卫：已登录用户不留在登录页（MVP 约定：完整守卫在 Task 3/4 业务页接入）
  useEffect(() => {
    if (getTokenPair()) {
      void Taro.reLaunch({ url: HOME_PAGE })
    }
  }, [])

  const switchMode = (m: Mode): void => {
    setMode(m)
    setError('')
  }

  const submit = async (): Promise<void> => {
    if (submitting) return
    const mail = email.trim()
    setError('')
    if (!mail) {
      setError('请输入邮箱')
      return
    }
    if (mode === 'register' && !nickname.trim()) {
      setError('请输入昵称')
      return
    }
    if (!password || password.length < 8) {
      setError('密码至少 8 位')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'register') {
        await register({ email: mail, nickname: nickname.trim(), password })
        await login({ email: mail, password }) // 注册即自动登录
      } else {
        await login({ email: mail, password })
      }
      await Taro.reLaunch({ url: HOME_PAGE })
    } catch (err) {
      const e = err as ApiError
      setError(e?.detail || String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View className="login-page">
      <View className="login-hero">
        <View className="login-logo">GL</View>
        <View className="login-title">
          {mode === 'login' ? (
            <>
              欢迎回来<Text className="em">！</Text>
            </>
          ) : (
            <>
              加入赶路咯<Text className="em">！</Text>
            </>
          )}
        </View>
        <View className="login-sub">让 AI 为你规划安全、合适的下一场山野徒步。</View>
      </View>

      {/* 登录 / 注册 切换 tab */}
      <View className="login-tabs">
        <View
          className={`login-tab${mode === 'login' ? ' on' : ''}`}
          onClick={() => switchMode('login')}
        >
          登录
        </View>
        <View
          className={`login-tab${mode === 'register' ? ' on' : ''}`}
          onClick={() => switchMode('register')}
        >
          注册
        </View>
      </View>

      <View className="field">
        <Text className="field-label">邮箱</Text>
        <View className="field-box">
          <Input
            className="field-input"
            type="text"
            placeholder="hiker@example.com"
            placeholderClass="field-placeholder"
            value={email}
            onInput={(e) => setEmail(e.detail.value)}
          />
        </View>
      </View>

      {mode === 'register' && (
        <View className="field">
          <Text className="field-label">昵称</Text>
          <View className="field-box">
            <Input
              className="field-input"
              type="text"
              placeholder="山野里的名字（最多 32 字）"
              placeholderClass="field-placeholder"
              value={nickname}
              onInput={(e) => setNickname(e.detail.value)}
            />
          </View>
        </View>
      )}

      <View className="field">
        <Text className="field-label">密码</Text>
        <View className="field-box">
          <Input
            className="field-input"
            password
            placeholder={mode === 'register' ? '至少 8 位' : '输入密码'}
            placeholderClass="field-placeholder"
            value={password}
            onInput={(e) => setPassword(e.detail.value)}
          />
        </View>
      </View>

      {error ? (
        <View className="login-error">
          <Text>{error}</Text>
        </View>
      ) : null}

      <View
        className={`btn btn-primary${submitting ? ' is-loading' : ''}`}
        onClick={submit}
      >
        {submitting ? '处理中…' : mode === 'login' ? '登 录' : '注 册 并 登 录'}
      </View>

      <View className="login-switch">
        {mode === 'login' ? '还没有账号？' : '已有账号？'}
        <Text className="login-switch-link" onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}>
          {mode === 'login' ? '马上注册' : '直接登录'}
        </Text>
      </View>
    </View>
  )
}
