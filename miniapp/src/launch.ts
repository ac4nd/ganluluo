/**
 * 启动序列（M8 Task 2，app 级一次性编排）：① 隐私政策 → ② 位置授权。
 *
 * 编排位置说明（Task brief 允许 app.ts 或入口页二选一）：序列状态（一次性标记）
 * 与弹窗 UI 分离——弹窗必须落在页面里渲染（Taro 没有 app 级浮层），所以编排
 * 函数放本模块，由入口页 index 的 useDidShow 触发 startLaunchSequence()；
 * 模块级 launchStarted 保证一次冷启动最多跑一遍（index 被反复 show 也不重弹）。
 * 已登录老用户同样走序列：gl_privacy_ok 标记独立于登录态。
 *
 * storage 标记：
 * - gl_privacy_ok   隐私政策已同意（一次性，永久生效）
 * - gl_loc_asked    位置授权弹窗已触发过（拒绝/失败也不重复弹）
 * - gl_loc          定位成功缓存 {latitude, longitude}（wgs84，供后续定位功能用）
 */
import Taro from '@tarojs/taro'

/** 隐私政策一次性同意标记 */
export const PRIVACY_KEY = 'gl_privacy_ok'
/** 位置授权弹窗已触发标记（防重复弹） */
export const LOC_ASKED_KEY = 'gl_loc_asked'
/** 定位成功缓存（wgs84） */
export const LOC_KEY = 'gl_loc'

/** 一次冷启动的序列只跑一遍（index 被反复 useDidShow 也不重弹） */
let launchStarted = false

/** 序列是否已触发过（诊断/测试用） */
export function isLaunchStarted(): boolean {
  return launchStarted
}

function hasFlag(key: string): boolean {
  try {
    return !!Taro.getStorageSync(key)
  } catch {
    return false
  }
}

function setFlag(key: string): void {
  try {
    Taro.setStorageSync(key, 1)
  } catch {
    /* storage 不可用时忽略：仅影响标记持久化，不阻塞主流程 */
  }
}

/**
 * 步骤②：触发平台位置授权弹窗（H5 = 浏览器 Geolocation 权限；
 * weapp = 微信 scope.userLocation 授权，app.config 已声明
 * permission + requiredPrivateInfos.getLocation）。
 * 拒绝/失败不阻塞（catch 静默，仅 console.warn 供排查；H5 dev server 的
 * http 非安全上下文或 headless 无授权都会走到这条路径）。
 * gl_loc_asked 在发起前置位：弹窗一次冷启动只出一次，用户拒绝后重启不再骚扰。
 */
export async function askLocationOnce(): Promise<void> {
  if (hasFlag(LOC_ASKED_KEY)) return
  setFlag(LOC_ASKED_KEY)
  try {
    const loc = await Taro.getLocation({ type: 'wgs84' })
    try {
      Taro.setStorageSync(LOC_KEY, { latitude: loc.latitude, longitude: loc.longitude })
    } catch {
      /* 坐标缓存失败不影响启动 */
    }
  } catch (err) {
    console.warn('[launch] getLocation 被拒或不可用（不阻塞）:', err)
  }
}

/**
 * 启动序列入口（入口页 index 的 useDidShow 里调用）：
 * - 已有隐私同意标记 → 直接续跑步骤②；
 * - 没有 → 回调 onPrivacyNeeded 让页面打开弹窗；用户点「同意并继续」后
 *   页面调 agreePrivacy() 写标记并续跑步骤②（点「不同意」则留在弹窗）。
 */
export function startLaunchSequence(onPrivacyNeeded: () => void): void {
  if (launchStarted) return
  launchStarted = true
  if (hasFlag(PRIVACY_KEY)) {
    void askLocationOnce()
  } else {
    onPrivacyNeeded()
  }
}

/** 用户在弹窗点「同意并继续」：写一次性标记并续跑步骤② */
export function agreePrivacy(): void {
  setFlag(PRIVACY_KEY)
  void askLocationOnce()
}
