App({
  onLaunch() {
    try {
      const oid = wx.getStorageSync('openId')
      if (oid) this.globalData.openId = oid
    } catch (e) {}
  },
  globalData: {
    apiBaseUrl: 'http://124.223.217.73:8080/api',
    openId: ''
  }
})
