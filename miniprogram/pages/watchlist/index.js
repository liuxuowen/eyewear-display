const app = getApp()

Page({
  data: {
    products: [],
    page: 1,
    hasMore: true,
    isLoading: false,
    empty: false
  },
  onShow() {
    // 同步选中自定义 tabBar 到“推荐”
    try {
      const tb = this.getTabBar && this.getTabBar()
      if (tb && tb.setSelectedByRoute) tb.setSelectedByRoute()
    } catch (e) {}
    try { if (app && app._log) app._log('watchlist:onShow', { route: (getCurrentPages().slice(-1)[0] || {}).route }) } catch (e) {}
    // 每次切换到推荐页，刷新列表
    this.setData({ products: [], page: 1, hasMore: true, empty: false }, () => this.loadFavorites())
  },
  loadFavorites() {
    if (this.data.isLoading || !this.data.hasMore) return
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) {
      this.setData({ empty: true })
      return
    }
    this.setData({ isLoading: true })
    wx.request({
      url: `${app.globalData.apiBaseUrl}/favorites`,
      method: 'GET',
      data: { open_id: oid, page: this.data.page, per_page: 10 },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const data = res.data.data || {}
          const items = data.items || []
          const pages = data.pages || 1
          const page = data.current_page || this.data.page
          const list = this.data.products.concat(items)
          this.setData({
            products: list,
            hasMore: page < pages,
            empty: list.length === 0
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
    if (this.data.hasMore) {
      this.setData({ page: this.data.page + 1 }, () => this.loadFavorites())
    }
  },
  onReachBottom() {
    this.loadMore()
  },
  onPullDownRefresh() {
    this.setData({ products: [], page: 1, hasMore: true, empty: false }, () => {
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
          const list = (this.data.products || []).filter(it => it.frame_model !== model)
          this.setData({ products: list, empty: list.length === 0 })
          wx.showToast({ title: '已取消推荐', icon: 'success' })
        } else {
          wx.showToast({ title: (res.data && res.data.message) || '操作失败', icon: 'none' })
        }
      },
      fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})