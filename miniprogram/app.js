App({
  onLaunch() {
    try {
      const oid = wx.getStorageSync('openId')
      if (oid) this.globalData.openId = oid
    } catch (e) {}
    // 自动登录（若本地无 openId）
    if (!this.globalData.openId) {
      this.loginIfNeeded().catch(() => {})
    }
  },

  // 确保拿到 openId；若已有则直接返回 Promise.resolve
  loginIfNeeded() {
    if (this.globalData.openId) return Promise.resolve(this.globalData.openId)
    if (this._loginPromise) return this._loginPromise

    this._loginPromise = new Promise((resolve, reject) => {
      wx.login({
        success: (res) => {
          const code = res.code
          if (!code) { reject(new Error('no code')); return }
          wx.request({
            url: `${this.globalData.apiBaseUrl}/wechat/code2session`,
            method: 'POST',
            data: { code },
            success: (r) => {
              const data = r && r.data
              const oid = data && data.status === 'success' && data.data && data.data.openid
              if (!oid) { reject(new Error('code2session failed')); return }
              this._setOpenId(oid)
              // 后台 upsert 一个占位用户
              wx.request({
                url: `${this.globalData.apiBaseUrl}/users/upsert`,
                method: 'POST',
                data: { open_id: oid }
              })
              resolve(oid)
            },
            fail: (e) => reject(e)
          })
        },
        fail: (e) => reject(e)
      })
    }).finally(() => {
      this._loginPromise = null
    })

    return this._loginPromise
  },

  _setOpenId(oid) {
    this.globalData.openId = oid
    try { wx.setStorageSync('openId', oid) } catch (e) {}
  },

  globalData: {
    apiBaseUrl: 'http://124.223.217.73:8080/api',
    openId: ''
  }
})
