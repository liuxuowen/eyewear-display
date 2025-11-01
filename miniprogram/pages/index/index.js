const app = getApp()
const config = require('../../config.js')

Page({
  onShow() {
    const track = (oid) => {
      if (!oid) return
      wx.request({
        url: `${app.globalData.apiBaseUrl}/analytics/pageview`,
        method: 'POST',
        data: { open_id: oid, page: '/pages/index/index' }
      })
    }
    if (app.globalData.openId) {
      track(app.globalData.openId)
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded().then(track).catch(() => {})
    }
  },

  data: {
    products: [],
    page: 1,
    hasMore: true,
    isLoading: false,
    searchQuery: '',
    searchField: (config && config.defaultSearchField) || 'frame_model'
  },

  onLoad() {
    this.loadProducts()
  },

  loadProducts() {
    const { page, isLoading, hasMore } = this.data
    if (isLoading) return
    if (!hasMore) return
    this.setData({ isLoading: true })
    wx.request({
      url: `${app.globalData.apiBaseUrl}/products`,
      data: (() => {
        const d = { page, per_page: 10 }
        const q = (this.data.searchQuery || '').trim()
        if (q) {
          d.search_field = this.data.searchField
          d.search_value = q
        }
        return d
      })(),
      success: (res) => {
        if (res.data.status === 'success') {
          const { items, total, pages } = res.data.data
          this.setData({
            products: this.data.products.concat(items || []),
            hasMore: page < pages
          })
        } else {
          wx.showToast({
            title: '加载失败',
            icon: 'none'
          })
        }
      },
      fail: () => {
        wx.showToast({
          title: '网络错误',
          icon: 'none'
        })
      },
      complete: () => {
        this.setData({ isLoading: false })
      }
    })
  },

  loadMore() {
    if (this.data.hasMore) {
      this.setData({
        page: this.data.page + 1
      }, () => {
        this.loadProducts()
      })
    }
  },

  // 触底自动加载下一页
  onReachBottom() {
    this.loadMore()
  },

  goToDetail(e) {
    const { model } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/product/detail?model=${model}`
    })
  },

  onPullDownRefresh() {
    this.setData({
      products: [],
      page: 1,
      hasMore: true
    }, () => {
      this.loadProducts()
      wx.stopPullDownRefresh()
    })
  },

  // 导航栏搜索框事件（微信内置）
  onNavigationBarSearchInputChanged(e) {
    const v = (e && (e.detail && (e.detail.value || e.detail.text))) || e.text || ''
    this.setData({ searchQuery: v })
  },

  onNavigationBarSearchInputConfirmed() {
    this._doSearch()
  },

  onNavigationBarSearchInputClicked() {
    // 可选：点击时展开搜索或展示历史
  },

  _doSearch() {
    // 重置分页并按条件重新加载
    this.setData({
      products: [],
      page: 1,
      hasMore: true
    }, () => this.loadProducts())
  }
})