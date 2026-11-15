/// <reference types="@tarojs/taro" />

// 全局类型：环境常量 + 资源/样式模块声明
declare namespace NodeJS {
  interface ProcessEnv {
    /** 构建期由 config/index.ts defineConstants 注入；为空时 client.ts 按端兜底 */
    GL_API_BASE?: string
    /** Taro 编译目标端 */
    TARO_ENV?: 'weapp' | 'h5' | 'alipay' | 'swan' | 'tt' | 'qq' | 'jd'
    NODE_ENV?: 'development' | 'production'
  }
}

declare module '*.png' {
  const src: string
  export default src
}
declare module '*.jpg' {
  const src: string
  export default src
}
declare module '*.jpeg' {
  const src: string
  export default src
}
declare module '*.gif' {
  const src: string
  export default src
}
declare module '*.webp' {
  const src: string
  export default src
}
declare module '*.svg' {
  const src: string
  export default src
}
declare module '*.css' {
  const styles: { [className: string]: string }
  export default styles
}
declare module '*.scss' {
  const styles: { [className: string]: string }
  export default styles
}
