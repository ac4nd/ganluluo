import path from 'path'

import { defineConfig, type UserConfigExport } from '@tarojs/cli'

import devConfig from './dev'
import prodConfig from './prod'

// https://taro-docs.jd.com/docs/config
// 合并模式：base + dev + prod 按 NODE_ENV 合并（defineConfig(merge)）。
export default defineConfig<'webpack5'>(async (merge) => {
  const baseConfig: UserConfigExport<'webpack5'> = {
    projectName: 'ganluluo-miniapp',
    date: '2026-11-16',
    designWidth: 750,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      375: 2,
      828: 1.81 / 2,
    },
    sourceRoot: 'src',
    outputRoot: 'dist',
    // tsconfig paths 对齐：@/ → src/
    alias: {
      '@': path.resolve(__dirname, '..', 'src'),
    },
    plugins: [],
    // 构建期常量注入：GL_API_BASE 可在构建前用环境变量覆盖（weapp 真机自测
    // 需要指向局域网 IP）。默认空串，src/api/client.ts 按端兜底。
    defineConstants: {
      'process.env.GL_API_BASE': JSON.stringify(process.env.GL_API_BASE || ''),
    },
    copy: {
      patterns: [],
      options: {},
    },
    framework: 'react',
    // compiler 用对象形式以便挂 prebundle 开关：Taro 4.1.11 的依赖预编译在
    // 本环境（Node 24 + webpack 5.91）创建 resolver 时报 roots.map / 写虚拟
    // 模块 _writeVirtualFile 崩溃（@tarojs/webpack5-prebundle bug），dev 直接
    // 走完整编译，只影响首次编译速度。
    compiler: {
      type: 'webpack5',
      prebundle: {
        enable: false,
      },
    },
    mini: {
      postcss: {
        pxtransform: {
          enable: true,
          config: {},
        },
        url: {
          enable: true,
          config: {
            limit: 1024, // 设定转换尺寸的上限
          },
        },
        // css modules 未启用（enable:false），不传 config（该字段在 4.1 类型里必填）
        cssModules: {
          enable: false,
        },
      },
    },
    h5: {
      publicPath: '/',
      router: {
        mode: 'browser',
        // 注意不要设 basename: '/'：Taro 4.1 的 @tarojs/router（universal-router）
        // 在 basename='/' 时会先把 pathname 掐掉首位 '/' 再匹配带前导斜杠的
        // route path，导致全部路由 404（页面空白）。basename 留默认（''）。
      },
      devServer: {
        port: 10086,
        // 后端 app/main.py 没有开 CORS 中间件：H5 dev 不能直连
        // http://127.0.0.1:8123（浏览器会拦截跨域响应），统一走 devServer
        // 同源代理转发到本地 uvicorn（curl http://127.0.0.1:10086/ops/health 验证）。
        proxy: {
          '/ops': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/auth': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/assistant': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/trips': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/routes': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/tracks': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/media': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/profile': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/gear': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/gear-list': { target: 'http://127.0.0.1:8123', changeOrigin: true },
          '/admin': { target: 'http://127.0.0.1:8123', changeOrigin: true },
        },
      },
      postcss: {
        autoprefixer: {
          enable: true,
          config: {},
        },
        // css modules 未启用（enable:false），不传 config（该字段在 4.1 类型里必填）
        cssModules: {
          enable: false,
        },
      },
    },
  }

  if (process.env.NODE_ENV === 'development') {
    return merge({}, baseConfig, devConfig)
  }
  return merge({}, baseConfig, prodConfig)
})
