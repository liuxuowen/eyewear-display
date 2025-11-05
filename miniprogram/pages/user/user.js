// pages/user/user.js
const app = getApp()

Page({
  data: {
    openId: '',
    nickname: '',
    avatarUrl: '',
    role: '', // 'sales' | 'user'
    isSales: false,
    hasMySales: false,
    mySalesName: '',
    referrals: [],
    kfSessionFrom: ''
  },

  onLoad() {
    const oid = app.globalData.openId || ''
    if (oid) {
      this.setData({ openId: oid })
      this._loadRole(oid)
      this._loadReferrals(oid)
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded().then((id) => {
        this.setData({ openId: id })
        this._loadRole(id)
        this._loadReferrals(id)
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
    // 同步选中自定义 tabBar 到“个人”
    try {
      const tb = this.getTabBar && this.getTabBar()
      if (tb && tb.setSelectedByRoute) tb.setSelectedByRoute()
    } catch (e) {}
    // 更新客服会话来源
    this._updateKfSessionFrom()
    try { if (app && app._log) app._log('user:onShow', { route: (getCurrentPages().slice(-1)[0] || {}).route }) } catch (e) {}
    if (app.globalData.openId && app.globalData.openId !== this.data.openId) {
      this.setData({ openId: app.globalData.openId })
      this._loadRole(app.globalData.openId)
      this._loadReferrals(app.globalData.openId)
    }
  },

  copyOpenId() {
    if (!this.data.openId) return
    wx.setClipboardData({
      data: this.data.openId,
      success: () => wx.showToast({ title: '已复制', icon: 'none' })
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
          const hasMySales = !!(res.data.data.has_my_sales || res.data.data.my_sales_open_id)
          const mySalesName = (res.data.data.my_sales_name || '').trim()
          this.setData({ role, isSales: role === 'sales', hasMySales, mySalesName })
          // 同步到全局，便于自定义 tabBar 响应
          if (app && app._setRoleFromServer) {
            app._setRoleFromServer(res.data.data)
          }
        }
      },
    })
  },

  _loadReferrals(openId) {
    if (!openId) return
    wx.request({
      url: `${app.globalData.apiBaseUrl}/users/referrals`,
      method: 'GET',
      data: { open_id: openId },
      success: (res) => {
        if (res.data && res.data.status === 'success' && res.data.data) {
          const items = res.data.data.items || []
          this.setData({ referrals: items })
        }
      }
    })
  },

  // 转发：带上推荐人 open_id
  onShareAppMessage() {
    const oid = app.globalData.openId || this.data.openId || ''
    const refParam = oid ? `?ref=${encodeURIComponent(oid)}` : ''
    const path = `/pages/index/index${refParam}`
    return {
      title: '给你推荐一个眼镜展示小程序',
      path
    }
  }
  ,
  // 与首页一致的客服 session-from 生成
  _updateKfSessionFrom() {
    try {
      const oid = app.globalData.openId || ''
      const now = new Date()
      const mm = String(now.getMonth() + 1).padStart(2, '0')
      const dd = String(now.getDate()).padStart(2, '0')
      const HH = String(now.getHours()).padStart(2, '0')
      const MM = String(now.getMinutes()).padStart(2, '0')
      const t = `${mm}/${dd}-${HH}:${MM}`
      const sanitize = (s) => {
        const x = (s || '').toString().replace(/[|]/g, '')
        return x.length > 8 ? x.slice(0, 8) : x
      }
      const apply = (salesName, refName) => {
        const sal = sanitize(salesName || '自然')
        const ref = sanitize(refName || '自然')
        const s = `sal:${sal}|ref:${ref}|t:${t}`
        this.setData({ kfSessionFrom: s })
      }
      if (!oid) { apply('自然', '自然'); return }
      wx.request({
        url: `${app.globalData.apiBaseUrl}/kf/context`,
        method: 'GET',
        data: { open_id: oid },
        success: (res) => {
          if (res && res.data && res.data.status === 'success' && res.data.data) {
            const salesName = res.data.data.sales_name || '自然'
            const refName = res.data.data.referrer_nickname || '自然'
            apply(salesName, refName)
          } else {
            apply('自然', '自然')
          }
        },
        fail: () => apply('自然', '自然')
      })
    } catch (e) {
      this.setData({ kfSessionFrom: 'sal:自然|ref:自然|t:0000-0000' })
    }
  }
})