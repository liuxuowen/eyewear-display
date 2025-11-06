App({
  onLaunch() {
    try {
      const oid = wx.getStorageSync('openId')
      if (oid) this.globalData.openId = oid
      // 预取上次缓存的角色标记，首屏用于自定义 tabBar 渲染
      const isSales = !!wx.getStorageSync('isSales')
      const hasMySales = !!wx.getStorageSync('hasMySales')
      const mySalesOpenId = wx.getStorageSync('mySalesOpenId') || ''
      const debug = !!wx.getStorageSync('debug')
      this.globalData.isSales = isSales
      this.globalData.hasMySales = hasMySales
      this.globalData.mySalesOpenId = mySalesOpenId
      this.globalData.debug = debug
      this._log('onLaunch:init', { oid, isSales, hasMySales, mySalesOpenId, debug })
    } catch (e) {}
    // 自动登录（若本地无 openId）
    if (!this.globalData.openId) {
      this.loginIfNeeded()
        .then(() => {
          // 登录后预取角色信息，便于自定义 tabBar 动态渲染
          this.fetchAndCacheRole().catch(() => {})
        })
        .catch(() => {})
    } else {
      // 已有 openId，尝试获取角色信息
      this.fetchAndCacheRole().catch(() => {})
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

  // 订阅-通知机制：角色变更时通知自定义 tabBar 等组件更新
  _roleListeners: [],
  // 调试日志（受 globalData.debug 控制）
  _log(tag, obj) {
    try { if (this.globalData && this.globalData.debug) console.log('[DBG]', tag, obj || '') } catch (e) {}
  },
  setDebug(on) {
    const v = !!on
    this.globalData.debug = v
    try { wx.setStorageSync('debug', v) } catch (e) {}
    this._log('setDebug', v)
  },
  addRoleListener(fn) {
    if (typeof fn === 'function' && this._roleListeners.indexOf(fn) === -1) {
      this._roleListeners.push(fn)
    }
  },
  removeRoleListener(fn) {
    const i = this._roleListeners.indexOf(fn)
    if (i >= 0) this._roleListeners.splice(i, 1)
  },
  _notifyRoleListeners() {
    const list = (this._roleListeners || []).slice()
    list.forEach(fn => { try { fn(this.globalData) } catch (e) {} })
  },

  // 从服务端获取并缓存角色信息
  fetchAndCacheRole() {
    const ensureLogin = () => this.loginIfNeeded ? this.loginIfNeeded() : Promise.resolve(this.globalData.openId)
    return ensureLogin().then((oid) => new Promise((resolve, reject) => {
      if (!oid) { reject(new Error('no openId')); return }
      this._log('fetchAndCacheRole:start', { oid })
      wx.request({
        url: `${this.globalData.apiBaseUrl}/users/role`,
        method: 'GET',
        data: { open_id: oid },
        success: (res) => {
          if (res && res.data && res.data.status === 'success' && res.data.data) {
            this._log('fetchAndCacheRole:success', res.data.data)
            this._setRoleFromServer(res.data.data)
            resolve(this.globalData)
          } else {
            this._log('fetchAndCacheRole:badResponse', res && res.data)
            reject(new Error('role api failed'))
          }
        },
        fail: (e) => { this._log('fetchAndCacheRole:fail', e); reject(e) }
      })
    }))
  },

  // 供页面在各自拉取到角色后写入全局并通知
  _setRoleFromServer(data) {
    try {
      const role = data && data.role
      const isSales = role === 'sales'
      const hasMySales = !!(data && (data.has_my_sales || data.my_sales_open_id))
      const mySalesOpenId = (data && data.my_sales_open_id) || ''
      this.globalData.isSales = !!isSales
      this.globalData.hasMySales = !!hasMySales
      this.globalData.mySalesOpenId = mySalesOpenId
      try {
        wx.setStorageSync('isSales', !!isSales)
        wx.setStorageSync('hasMySales', !!hasMySales)
        wx.setStorageSync('mySalesOpenId', mySalesOpenId || '')
      } catch (e) {}
      this._log('_setRoleFromServer', { role, isSales, hasMySales, mySalesOpenId })
      this._notifyRoleListeners()
    } catch (e) {}
  },

  globalData: {
    apiBaseUrl: 'https://yimuliaoran.top/api',
    openId: '',
    // 角色相关全局状态（供自定义 tabBar 动态渲染）
    isSales: false,
    hasMySales: false,
    mySalesOpenId: '',
    // 调试开关
    debug: false
  }
})
