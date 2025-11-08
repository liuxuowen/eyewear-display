// pages/user/user.js
const app = getApp()

Page({
  data: {
    openId: '',
    nickname: '',
    avatarUrl: '',
  avatarDebug: '',
    editNickname: '',
    nicknameHint: '',
    role: '', // 'sales' | 'user'
    isSales: false,
    hasMySales: false,
    mySalesName: '',
    referrals: [],
    kfSessionFrom: '',
    // 已简化为一键获取并直接保存，不再使用草稿字段
  },

  onLoad() {
    const oid = app.globalData.openId || ''
    if (oid) {
      this.setData({ openId: oid })
      this._loadRole(oid)
      this._loadReferrals(oid)
      this._loadProfile(oid)
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded().then((id) => {
        this.setData({ openId: id })
        this._loadRole(id)
        this._loadReferrals(id)
        this._loadProfile(id)
      }).catch(() => {})
    }
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
      this._loadProfile(app.globalData.openId)
    }
  },

  copyOpenId() {
    if (!this.data.openId) return
    wx.setClipboardData({
      data: this.data.openId,
      success: () => wx.showToast({ title: '已复制', icon: 'none' })
    })
  },

  // 注：平台规则调整后不再使用 getUserProfile 获取昵称头像，此方法已移除。

  // 分离：仅获取昵称
  getNickname() {
    // 根据官方最佳实践：不再依赖 getUserProfile 返回昵称，改为手动输入+保存
    wx.showToast({ title: '请输入上方昵称后保存', icon: 'none' })
  },

  // 分离：仅获取头像（使用 chooseAvatar）
  onChooseAvatar(e) {
    try {
      const url = e.detail && e.detail.avatarUrl
      if (!url) { wx.showToast({ title: '未获取到头像', icon: 'none' }); return }
      const oid = app.globalData.openId || this.data.openId
      if (!oid) { wx.showToast({ title: '未获取到用户ID', icon: 'none' }); return }
      // 上传临时头像文件，换取长期可访问 URL
      wx.uploadFile({
        url: `${app.globalData.apiBaseUrl}/upload/avatar`,
        filePath: url,
        name: 'file',
        formData: { open_id: oid },
        success: (res) => {
          try {
            const data = JSON.parse(res.data || '{}')
            if (data && data.status === 'success' && data.url) {
              const publicUrl = data.url
              this.setData({ avatarUrl: publicUrl })
              try { wx.setStorageSync('avatarUrl', publicUrl) } catch (err) {}
              this._probeAvatar(publicUrl)
              // 保存，仅头像更新（静默）
              this._upsertProfile(this.data.nickname, publicUrl, { silent: true })
              wx.showToast({ title: '头像已更新', icon: 'none' })
            } else {
              wx.showToast({ title: '上传失败', icon: 'none' })
            }
          } catch (err) {
            wx.showToast({ title: '解析失败', icon: 'none' })
          }
        },
        fail: (err) => {
          console.error('avatar upload fail', err)
          wx.showToast({ title: '网络错误', icon: 'none' })
        }
      })
    } catch (er) {
      wx.showToast({ title: '头像获取异常', icon: 'none' })
    }
  },

  // 手动输入昵称
  onEditNicknameInput(e) {
    const v = (e && e.detail && e.detail.value) || ''
    this.setData({ editNickname: v, nicknameHint: '' })
    // 防抖自动保存，解决选择微信昵称后未失焦不触发保存的问题
    this._clearNickTimer()
    const val = (v || '').trim()
    // 基本长度通过再触发保存，避免无效请求
    this._nickTimer = setTimeout(() => {
      if (val && val.length >= 2 && val.length <= 12) {
        this._autoSaveNickname(val, { silent: true, source: 'input' })
      }
    }, 600)
  },
  // 输入完成自动保存：失焦
  onNicknameBlur(e) {
    const v = (e && e.detail && (e.detail.value || e.detail.cursor !== undefined ? e.detail.value : '')) || ''
    this._clearNickTimer()
    this._autoSaveNickname((v || '').trim(), { silent: false, source: 'blur' })
  },
  // 输入法完成键
  onNicknameConfirm(e) {
    const v = (e && e.detail && e.detail.value) || ''
    this._clearNickTimer()
    this._autoSaveNickname((v || '').trim(), { silent: false, source: 'confirm' })
  },
  _clearNickTimer() {
    if (this._nickTimer) {
      clearTimeout(this._nickTimer)
      this._nickTimer = null
    }
  },
  // 自动保存逻辑（校验+避免重复保存）
  _autoSaveNickname(nn, opts = {}) {
    const prev = (this.data.nickname || '').trim()
    const draft = (this.data.editNickname || '').trim()
    // 同步草稿
    if (nn !== draft) {
      this.setData({ editNickname: nn })
    }
    if (!nn) { this.setData({ nicknameHint: '请输入昵称' }); return }
    if (nn.length < 2 || nn.length > 12) { wx.showToast({ title: '长度 2-12 个字符', icon: 'none' }); return }
    if (nn === prev) { this.setData({ nicknameHint: '昵称已保存' }); return }
    try { wx.setStorageSync('nickname', nn) } catch (e) {}
    this._upsertProfile(nn, this.data.avatarUrl, { silent: !!opts.silent })
    this.setData({ nickname: nn, nicknameHint: '昵称已保存' })
  },
  
  applyNickname() {
    const nn = (this.data.editNickname || '').trim()
    if (!nn) { wx.showToast({ title: '请输入昵称', icon: 'none' }); return }
    if (nn.length < 2 || nn.length > 12) { wx.showToast({ title: '长度 2-12 个字符', icon: 'none' }); return }
    try { wx.setStorageSync('nickname', nn) } catch (e) {}
    this._upsertProfile(nn, this.data.avatarUrl)
    this.setData({ nickname: nn, nicknameHint: '昵称已保存' })
    wx.showToast({ title: '昵称已保存', icon: 'none' })
  },

  onAvatarLoad(e) {
    this.setData({ avatarDebug: '头像加载成功' })
  },
  onAvatarError(e) {
    this.setData({ avatarDebug: '头像加载失败(code:' + (e && e.detail && e.detail.errMsg || '未知') + ')' })
  },

  _probeAvatar(url) {
    if (!url) return
    try {
      wx.getImageInfo({
        src: url,
        success: () => {
          this.setData({ avatarDebug: '头像可访问' })
        },
        fail: (err) => {
          this.setData({ avatarDebug: '下载失败:' + (err && err.errMsg || 'unknown') })
        }
      })
    } catch (e) {
      this.setData({ avatarDebug: '探测异常' })
    }
  },

    _upsertProfile(nn, av, opts = {}) {
      const ensureLogin = app.loginIfNeeded ? app.loginIfNeeded() : Promise.resolve(app.globalData.openId)
      ensureLogin.then((oid) => {
        if (!oid) { wx.showToast({ title: '未获取到用户ID', icon: 'none' }); return }
        wx.request({
          url: `${app.globalData.apiBaseUrl}/users/upsert`,
          method: 'POST',
          data: { open_id: oid, nickname: nn, avatar_url: av },
          success: (r) => {
            const ok = r && r.data && r.data.status === 'success'
            if (!opts.silent) {
              if (ok) wx.showToast({ title: '已保存', icon: 'success' })
              else wx.showToast({ title: '保存失败', icon: 'none' })
            }
            // 如果没有手动输入昵称且后台返回用户已有昵称，自动填充（后期可扩展 GET profile 接口）
            if (!nn && r && r.data && r.data.data && r.data.data.nickname) {
              const autoNick = r.data.data.nickname
              if (autoNick && !this.data.nickname) {
                this.setData({ nickname: autoNick })
                try { wx.setStorageSync('nickname', autoNick) } catch (e) {}
              }
            }
          },
          fail: () => {
            if (!opts.silent) wx.showToast({ title: '网络错误', icon: 'none' })
          }
        })
      }).catch(() => wx.showToast({ title: '登录失败', icon: 'none' }))
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

  _loadProfile(openId) {
    if (!openId) return
    wx.request({
      url: `${app.globalData.apiBaseUrl}/users/profile`,
      method: 'GET',
      data: { open_id: openId },
      success: (res) => {
        if (res && res.data && res.data.status === 'success' && res.data.data) {
          const nick = (res.data.data.nickname || '').trim()
          const avatar = (res.data.data.avatar_url || '').trim()
          const upd = {}
          if (nick) upd.nickname = nick
          if (avatar) upd.avatarUrl = avatar
          if (Object.keys(upd).length) this.setData(upd)
        }
      }
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