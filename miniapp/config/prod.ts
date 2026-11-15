import { defineConfig, type UserConfigExport } from '@tarojs/cli'

export default defineConfig<'webpack5'>(async (merge) => {
  const config: UserConfigExport<'webpack5'> = {
    mini: {},
    h5: {},
  }
  return merge({}, config)
})
