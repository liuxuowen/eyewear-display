const app = getApp()

Page({
  data: {
    // 分组后的批次数据：[{ batch_id, batch_time, items: [product...] }]
    batches: [],
    // 兼容旧字段（如果需要原列表，可由 batches 扁平化得到）
    products: [],
    page: 1,
    hasMore: true,
    isLoading: false,
    empty: false,
    hasMySales: false,
    isSales: false,
    mySalesName: '',
    mySalesOpenId: '',
    totalCount: 0,
    // 销售分享备注（0-10字）
    salesShareNote: '' ,
    // 分享包准备状态（用于 watchlist 一键打包）
    isSharePreparedAll: false,
    preparedShareAllId: 0,
    preparedAllSkusKey: '',
    // 图片加载覆盖映射：原图URL => 当前使用的src（thumb或原图）
    imageSrcMap: {},
    // 图片是否完成加载（用于渐显）
    imageLoadedMap: {}
  },
  onLoad(options) {
    // 计算状态栏与胶囊按钮，精确适配不同机型
    try {
      const sys = wx.getSystemInfoSync()
      const menu = wx.getMenuButtonBoundingClientRect ? wx.getMenuButtonBoundingClientRect() : null
      const statusBarHeight = sys.statusBarHeight || 20
      let navBarHeight = 44
      if (menu && menu.top && menu.height) {
        // 导航栏高度 = 两倍(菜单顶部到状态栏底部的间距) + 胶囊高度
        navBarHeight = (menu.top - statusBarHeight) * 2 + menu.height
      }
      const navHeight = statusBarHeight + navBarHeight
      this.setData({ statusBarHeight, navBarHeight, navHeight })
    } catch (e) {}
  },
  onShow() {
    // 同步选中自定义 tabBar 到“推荐”
    try {
      const tb = this.getTabBar && this.getTabBar()
      if (tb && tb.setSelectedByRoute) tb.setSelectedByRoute()
    } catch (e) {}
    // 页面曝光上报
    const pagePath = '/pages/watchlist/index'
    const track = (oid) => {
      if (!oid) return
      try {
        wx.request({
          url: `${app.globalData.apiBaseUrl}/analytics/pageview`,
          method: 'POST',
          data: { open_id: oid, page: pagePath }
        })
      } catch (_) {}
    }
    if (app.globalData && app.globalData.openId) {
      track(app.globalData.openId)
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded().then(track).catch(() => {})
    }
    // 若仅从全屏图片预览返回，避免触发整页刷新
    if (this._skipNextOnShow) {
      this._skipNextOnShow = false
      try { if (app && app._log) app._log('watchlist:onShow:skip-refresh-after-preview') } catch (e) {}
      return
    }
    try { if (app && app._log) app._log('watchlist:onShow', { route: (getCurrentPages().slice(-1)[0] || {}).route }) } catch (e) {}
    // 每次切换到推荐页，刷新列表
    this._syncRoleFromGlobal()
    this.setData({ batches: [], products: [], page: 1, hasMore: false, empty: false, totalCount: 0 }, () => this.loadFavorites())
  },
  // 缩略图加载失败时，回退到原图
  onImageError(e) {
    try {
      const img = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.img) || ''
      if (!img) return
      const map = Object.assign({}, this.data.imageSrcMap || {})
      // 回退到原图
      map[img] = img
      this.setData({ imageSrcMap: map })
    } catch (_) {}
  },
  onImageLoad(e) {
    try {
      const img = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.img) || ''
      if (!img) return
      const loaded = Object.assign({}, this.data.imageLoadedMap || {})
      loaded[img] = true
      this.setData({ imageLoadedMap: loaded })
    } catch (_) {}
  },
  _syncRoleFromGlobal() {
    try {
      const gd = (getApp() && getApp().globalData) || {}
      const hasMySales = !!gd.hasMySales
      const mySalesOpenId = gd.mySalesOpenId || ''
      const isSales = !!gd.isSales
      // 若全局中没有销售姓名，尝试后端拉取角色补齐（与首页逻辑保持一致）
      if ((!gd.mySalesName || typeof gd.isSales !== 'boolean') && (mySalesOpenId || gd.openId)) {
        wx.request({
          url: `${gd.apiBaseUrl}/users/role`,
          method: 'GET',
          data: { open_id: (gd.openId || '') },
          success: (res) => {
            const d = res && res.data && res.data.data
            if (d && d.my_sales_name) {
              this.setData({ mySalesName: d.my_sales_name })
            }
            if (d && d.role) {
              this.setData({ isSales: d.role === 'sales' })
            }
          }
        })
      }
      this.setData({
        hasMySales,
        mySalesOpenId,
        mySalesName: gd.mySalesName || '',
        isSales: typeof this.data.isSales === 'boolean' ? this.data.isSales : isSales
      })
    } catch (e) {}
  },
  loadFavorites() {
    if (this.data.isLoading) return
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) {
      this.setData({ empty: true })
      return
    }
    this.setData({ isLoading: true })
    wx.request({
      url: `${app.globalData.apiBaseUrl}/favorites`,
      method: 'GET',
      data: { open_id: oid, group_by: 'batch' },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const data = res.data.data || {}
          const batches = Array.isArray(data.batches) ? data.batches : []
          // 统计总数
          const total = batches.reduce((acc, b) => acc + (Array.isArray(b.items) ? b.items.length : 0), 0)
          // 兼容：扁平化为 products 以便后续可能复用
          const flat = [].concat(...batches.map(b => (b.items || [])))
          this.setData({
            batches,
            products: flat,
            hasMore: false,
            empty: total === 0,
            totalCount: total
          })
        } else {
          wx.showToast({ title: '加载失败', icon: 'none' })
        }
      },
      fail: () => wx.showToast({ title: '网络错误', icon: 'none' }),
      complete: () => this.setData({ isLoading: false })
    })
  },
  loadMore() {
    // 分组模式不分页，留空占位
  },
  onReachBottom() {
    this.loadMore()
  },
  onPullDownRefresh() {
    this.setData({ batches: [], products: [], page: 1, hasMore: false, empty: false, totalCount: 0 }, () => {
      this.loadFavorites()
      wx.stopPullDownRefresh()
    })
  },
  goToDetail(e) {
    const { model } = e.currentTarget.dataset
    if (!model) return
    wx.navigateTo({ url: `/pages/product/detail?model=${model}` })
  },
  removeFavorite(e) {
    const model = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.model) || ''
    if (!model) return
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    wx.request({
      url: `${app.globalData.apiBaseUrl}/favorites`,
      method: 'DELETE',
      data: { open_id: oid, frame_model: model },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          // 从 batches 中移除
          const batches = (this.data.batches || []).map(b => ({
            ...b,
            items: (b.items || []).filter(it => it.frame_model !== model)
          })).filter(b => (b.items || []).length > 0)
          const total = batches.reduce((acc, b) => acc + (b.items ? b.items.length : 0), 0)
          // 同时维护扁平化列表
          const flat = [].concat(...batches.map(b => (b.items || [])))
          this.setData({ batches, products: flat, empty: total === 0, totalCount: total })
          wx.showToast({ title: '已取消推荐', icon: 'success' })
        } else {
          wx.showToast({ title: (res.data && res.data.message) || '操作失败', icon: 'none' })
        }
      },
      fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
  ,
  // 一键清空（仅销售可见）
  clearAllFavorites() {
    if (!this.data.isSales) { wx.showToast({ title: '仅销售可用', icon: 'none' }); return }
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) { wx.showToast({ title: '请先登录', icon: 'none' }); return }
    wx.showModal({
      title: '确认清空',
      content: '确定清空全部推荐？此操作不可撤销',
      confirmText: '清空',
      confirmColor: '#ff4d4f',
      success: (res) => {
        if (!res.confirm) return
        wx.request({
          url: `${app.globalData.apiBaseUrl}/favorites/batch`,
          method: 'POST',
          data: { open_id: oid, frame_models: [], reset: true },
          success: (r) => {
            if (r && r.data && r.data.status === 'success') {
              this.setData({ batches: [], products: [], empty: true, totalCount: 0 })
              wx.showToast({ title: '已清空推荐', icon: 'success' })
            } else {
              wx.showToast({ title: '清空失败', icon: 'none' })
            }
          },
          fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
        })
      }
    })
  },
  // 输入备注
  onNoteInput(e) {
    let v = (e.detail && e.detail.value) || ''
    if (v.length > 10) v = v.slice(0, 10)
    this.setData({ salesShareNote: v })
  },
  _computeKeyForAll(skus, sid, note) {
    try {
      const arr = (skus || []).slice().sort()
      return `${sid||''}::${arr.join(',')}::${note||''}`
    } catch (e) { return `${sid||''}::${note||''}` }
  },
  _getAllRecommendedSkus(limit=50) {
    const list = (this.data.products || []).map(p => p.frame_model).filter(Boolean)
    if (!Array.isArray(list)) return []
    // 去重并裁剪上限
    const seen = {}
    const out = []
    for (let i=0;i<list.length && out.length<limit;i++) {
      const m = (list[i]||'').trim()
      if (!m || seen[m]) continue
      seen[m] = true
      out.push(m)
    }
    return out
  },
  // 预生成整包分享记录，供 open-type=share 使用 shid
  prepareShareAllPackage() {
    if (!this.data.isSales) { wx.showToast({ title: '仅销售可用', icon: 'none' }); return }
    const skus = this._getAllRecommendedSkus(50)
    if (!skus.length) { wx.showToast({ title: '暂无可分享商品', icon: 'none' }); return }
    const sid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!sid) { wx.showToast({ title: '请先登录', icon: 'none' }); return }
    const note = (this.data.salesShareNote || '').trim()
    const baseKey = this._computeKeyForAll(skus, sid, note)
    const ts = Math.floor(Date.now()/1000)
    const dedup_key = `${baseKey}::${ts}`
    // 预创建分享记录以便在 path 中带上 shid，后续可精确统计 open_count
    wx.request({
      url: `${app.globalData.apiBaseUrl}/shares/push`,
      method: 'POST',
      data: { salesperson_open_id: sid, product_list: skus, note, dedup_key },
      success: (res) => {
        if (res && res.data && res.data.status === 'success' && res.data.data && res.data.data.id) {
          const shareId = res.data.data.id
          // preparedAllSkusKey 仅保存 baseKey，用于判断选择是否变化；dedup_key 包含时间保证唯一
          this.setData({ isSharePreparedAll: true, preparedShareAllId: shareId, preparedAllSkusKey: baseKey })
        }
      }
    })
  },
  onShareAppMessage() {
    // 一键打包转发（整包当前推荐列表）
    const isSales = !!this.data.isSales
    const sid = (getApp().globalData && getApp().globalData.openId) || ''
    const skus = this._getAllRecommendedSkus(50)
    const count = skus.length
    let title = count > 0 ? `推荐${count}款镜架` : '精品镜架推荐'
    let path = '/pages/index/index'
    if (!isSales || !sid || count === 0) {
      return { title, path, imageUrl: '/images/watchlist/recommend.png' }
    }
    const encSkus = encodeURIComponent(skus.join(','))
    const sidEnc = encodeURIComponent(sid)
    const note = (this.data.salesShareNote || '').trim()
    const currentBaseKey = this._computeKeyForAll(skus, sid, note)
    if (this.data.isSharePreparedAll && this.data.preparedShareAllId > 0 && this.data.preparedAllSkusKey === currentBaseKey) {
      const shid = this.data.preparedShareAllId
      path = `/pages/index/index?skus=${encSkus}&sid=${sidEnc}&shid=${shid}`
      // 标记发送
      wx.request({ url: `${app.globalData.apiBaseUrl}/shares/mark_sent`, method: 'POST', data: { share_id: shid } })
    } else {
      // 未预生成则尽力登记（无法保证 shid 带入路径）
      const ts = Math.floor(Date.now()/1000)
      const dedup_key = `${currentBaseKey}::${ts}`
      const sig = encodeURIComponent(dedup_key)
      path = `/pages/index/index?skus=${encSkus}&sid=${sidEnc}&sig=${sig}`
      wx.request({ url: `${app.globalData.apiBaseUrl}/shares/push`, method: 'POST', data: { salesperson_open_id: sid, product_list: skus, note, dedup_key },
        success: (res) => {
          if (res && res.data && res.data.status === 'success' && res.data.data && res.data.data.id) {
            const shareId = res.data.data.id
            wx.request({ url: `${app.globalData.apiBaseUrl}/shares/mark_sent`, method: 'POST', data: { share_id: shareId } })
          }
        }
      })
    }
    return { title, path, imageUrl: '/images/watchlist/recommend.png' }
  },
  // 图片全屏预览
  previewImage(e) {
    const cur = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.current) || ''
    let list = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.list) || []
    const model = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.model) || ''
    if (typeof list === 'string') {
      // dataset 把数组序列化为逗号拼接字符串的情况
      list = list.split(',').map(s => s.trim()).filter(Boolean)
    }
    if (!Array.isArray(list) || list.length === 0) list = [cur].filter(Boolean)
    if (!cur) return
    // 上报一次图片预览 PV（包含 frame_model 作为查询参数，便于后台识别）
    try {
      const oid = (getApp() && getApp().globalData && getApp().globalData.openId) || ''
      if (oid) {
        const qp = model ? `?model=${encodeURIComponent(model)}` : ''
        wx.request({
          url: `${app.globalData.apiBaseUrl}/analytics/pageview`,
          method: 'POST',
          data: { open_id: oid, page: `/pages/watchlist/preview${qp}` }
        })
      }
    } catch (_) {}
    // 标记：从预览返回时跳过一次 onShow 刷新
    this._skipNextOnShow = true
    wx.previewImage({ current: cur, urls: list })
  }
})