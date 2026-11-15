// Taro babel preset：React 框架 + TS，webpack5 编译器
module.exports = {
  presets: [
    ['taro', {
      framework: 'react',
      ts: true,
      compiler: 'webpack5',
    }],
  ],
}
