export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/login/index',
    'pages/wechat-login/index',
    'pages/profile/index',
    'pages/gear/index',
    'pages/onboard/sport/index',
    'pages/onboard/exp/index',
    'pages/routes/index',
    'pages/route-detail/index',
    'pages/chat/index',
    'pages/trips/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#0c110a',
    navigationBarTitleText: '赶路咯',
    navigationBarTextStyle: 'white',
  },
  /* M8 Task 2：启动序列②的 Taro.getLocation 在 weapp 端需要这两处声明，
     否则基础库直接 fail（api scope is not declared）。 */
  permission: {
    'scope.userLocation': {
      desc: '你的位置信息将用于路线匹配与行程定位，拒绝授权不影响核心功能',
    },
  },
  requiredPrivateInfos: ['getLocation'],
})
