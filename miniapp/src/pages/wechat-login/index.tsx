/**
 * 微信一键登录页（M8 Task 2）：
 * - weapp：品牌区 + 协议勾选框（未勾选点登录 → toast「请先同意协议」并保留在页）
 *   + 微信绿大按钮「微信一键登录」→ Taro.login() 取 code → POST /auth/wechat-login
 *   （api/auth.wechatLogin 内部 setTokenPair）→ reLaunch 首页；失败显 detail 错误条；
 *   loading 防重复提交。
 * - H5：Taro.login 不可用（无微信运行时）→ 整页降级卡「一键登录请使用微信小程序
 *   打开」+ 返回邮箱登录链接；不渲染勾选框与登录按钮（process.env.TARO_ENV 编译期
 *   分支，weapp JSX 在 H5 构建里被剔除）。
 */
import { useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import { wechatLogin } from '@/api/auth'
import { HOME_PAGE, LOGIN_PAGE, type ApiError } from '@/api/client'
import './index.scss'

const isWeapp = process.env.TARO_ENV === 'weapp'

export default function WechatLogin() {
  const [agreed, setAgreed] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  /** 返回邮箱登录：正常从 login 页 navigateTo 进来走返回；深链直达则 reLaunch 兜底 */
  const backToEmailLogin = (): void => {
    void Taro.navigateBack().catch(() => void Taro.reLaunch({ url: LOGIN_PAGE }))
  }

  const submit = async (): Promise<void> => {
    if (submitting) return
    if (!agreed) {
      void Taro.showToast({ title: '请先同意协议', icon: 'none', duration: 2000 })
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const { code } = await Taro.login()
      await wechatLogin(code) // 成功即写登录态（api/auth 内 setTokenPair）
      await Taro.reLaunch({ url: HOME_PAGE })
    } catch (err) {
      const e = err as ApiError
      setError(e?.detail || String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View className="wxlogin-page">
      {/* 品牌区 */}
      <View className="wxlogin-brand">
        <View className="wxlogin-logo">GL</View>
        <View className="wxlogin-title">微信一键登录</View>
        <View className="wxlogin-sub">免注册，用微信身份直接进入赶路咯的山野规划。</View>
      </View>

      {isWeapp ? (
        <>
          {/* 协议勾选（原型 01 的同意元素）：未勾选点登录 → toast 并保留在页 */}
          <View className="wxlogin-check" onClick={() => setAgreed(!agreed)}>
            <View className={`wxlogin-checkbox${agreed ? ' on' : ''}`}>{agreed ? '✓' : ''}</View>
            <Text className="wxlogin-check-text">
              已阅读并同意
              <Text className="wxlogin-link">《用户协议》</Text>
              与
              <Text className="wxlogin-link">《隐私政策》</Text>
            </Text>
          </View>

          {error ? (
            <View className="wxlogin-error">
              <Text>{error}</Text>
            </View>
          ) : null}

          {/* 微信绿大按钮 */}
          <View
            className={`wxlogin-btn${submitting ? ' is-loading' : ''}`}
            onClick={() => void submit()}
          >
            {submitting ? '登录中…' : '微信一键登录'}
          </View>

          <View className="wxlogin-alt" onClick={backToEmailLogin}>
            使用邮箱密码登录
          </View>
        </>
      ) : (
        /* H5 降级卡：Taro.login 无微信运行时支撑，整页降级 */
        <View className="wxlogin-degrade">
          <View className="wxlogin-degrade-badge">微</View>
          <View className="wxlogin-degrade-title">一键登录请使用微信小程序打开</View>
          <View className="wxlogin-degrade-desc">
            当前在浏览器环境中，微信登录能力不可用。请在微信中打开「赶路咯」小程序体验一键登录，或继续使用邮箱密码登录。
          </View>
          <View className="wxlogin-degrade-link" onClick={backToEmailLogin}>
            返回邮箱登录
          </View>
        </View>
      )}
    </View>
  )
}
