// pages/user/user.js
const app = getApp()

Page({
  data: {
    openId: ''
  },

  onLoad() {
    const oid = app.globalData.openId || ''
    if (oid) this.setData({ openId: oid })
  },

  onShow() {
    if (app.globalData.openId && app.globalData.openId !== this.data.openId) {
      this.setData({ openId: app.globalData.openId })
    }
  },

  copyOpenId() {
    if (!this.data.openId) return
    wx.setClipboardData({
      data: this.data.openId,
      success: () => wx.showToast({ title: '已复制', icon: 'none' })
    })
  },

  fetchOpenId() {
    // 通过 wx.login 获取 code，调用后端 /api/wechat/code2session 获取 openid
    wx.login({
      success: (res) => {
        const code = res.code
        if (!code) {
          wx.showToast({ title: '获取code失败', icon: 'none' })
          return
        }
        wx.request({
          url: `${app.globalData.apiBaseUrl}/wechat/code2session`,
          method: 'POST',
          data: { code },
          success: (r) => {
            if (r.data && r.data.status === 'success' && r.data.data && r.data.data.openid) {
              const oid = r.data.data.openid
              app.globalData.openId = oid
              try { wx.setStorageSync('openId', oid) } catch (e) {}
              this.setData({ openId: oid })
            } else {
              wx.showToast({ title: '获取openid失败', icon: 'none' })
            }
          },
          fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
        })
      },
      fail: () => wx.showToast({ title: 'wx.login失败', icon: 'none' })
    })
  }
})