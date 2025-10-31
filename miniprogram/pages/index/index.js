const app = getApp()

Page({
  onShow() {
    const openId = app.globalData.openId
    if (!openId) return
    wx.request({
      url: `${app.globalData.apiBaseUrl}/analytics/pageview`,
      method: 'POST',
      data: {
        open_id: openId,
        page: '/pages/index/index' // 或者动态传 this.route
      }
    })
  },

  data: {
    products: [],
    page: 1,
    hasMore: true,
    isLoading: false
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
      data: {
        page: page,
        per_page: 10
      },
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
  }
})