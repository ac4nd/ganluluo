import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import './app.scss'

/**
 * 应用入口（Taro 4 React）。
 * 构建期由 @tarojs/plugin-framework-react 把本组件经 @tarojs/react 的
 * createReactApp 装配为各端运行时入口（dist/app.js 注入 createReactApp 调用）。
 */
function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    console.log('[ganluluo-miniapp] launched @', process.env.TARO_ENV)
  })

  // children 是即将渲染的页面，需要原样返回
  return children
}

export default App
