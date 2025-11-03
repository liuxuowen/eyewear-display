// pages/user/user.js
const app = getApp()

Page({
  data: {
    openId: '',
    nickname: '',
    avatarUrl: '',
    role: '', // 'sales' | 'user'
    isSales: false
  },

  onLoad() {
    const oid = app.globalData.openId || ''
    if (oid) {
      this.setData({ openId: oid })
      this._loadRole(oid)
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded().then((id) => {
        this.setData({ openId: id })
        this._loadRole(id)
      }).catch(() => {})
    }
    // 从本地读取已保存的昵称、头像
    try {
      const nn = wx.getStorageSync('nickname')
      const av = wx.getStorageSync('avatarUrl')
      if (nn) this.setData({ nickname: nn })
      if (av) this.setData({ avatarUrl: av })
    } catch (e) {}
  },

  onShow() {
    if (app.globalData.openId && app.globalData.openId !== this.data.openId) {
      this.setData({ openId: app.globalData.openId })
      this._loadRole(app.globalData.openId)
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
              // 同步到后端用户表（占位 upsert）
              wx.request({
                url: `${app.globalData.apiBaseUrl}/users/upsert`,
                method: 'POST',
                data: { open_id: oid }
              })
            } else {
              wx.showToast({ title: '获取openid失败', icon: 'none' })
            }
          },
          fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
        })
      },
      fail: () => wx.showToast({ title: 'wx.login失败', icon: 'none' })
    })
  },

  getProfile() {
    if (!wx.getUserProfile) {
      wx.showModal({ title: '提示', content: '微信版本过低，不支持获取用户信息，请升级微信版本', showCancel: false })
      return
    }
    wx.getUserProfile({
      desc: '用于完善个人资料',
      success: (res) => {
        const info = res && res.userInfo
        if (!info) return
        const nn = info.nickName || ''
        const av = info.avatarUrl || ''
        this.setData({ nickname: nn, avatarUrl: av })
        try { wx.setStorageSync('nickname', nn); wx.setStorageSync('avatarUrl', av) } catch (e) {}
        const ensureLogin = app.loginIfNeeded ? app.loginIfNeeded() : Promise.resolve(app.globalData.openId)
        ensureLogin.then((oid) => {
          if (!oid) return
          wx.request({
            url: `${app.globalData.apiBaseUrl}/users/upsert`,
            method: 'POST',
            data: { open_id: oid, nickname: nn, avatar_url: av }
          })
        }).catch(() => {})
      },
      fail: () => {
        wx.showToast({ title: '用户未授权', icon: 'none' })
      }
    })
  },

  _loadRole(openId) {
    if (!openId) return
    wx.request({
      url: `${app.globalData.apiBaseUrl}/users/role`,
      method: 'GET',
      data: { open_id: openId },
      success: (res) => {
        if (res.data && res.data.status === 'success' && res.data.data) {
          const role = res.data.data.role || 'user'
          this.setData({ role, isSales: role === 'sales' })
        }
      }
    })
  }
})