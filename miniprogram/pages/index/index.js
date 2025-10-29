const app = getApp()

Page({
  data: {
    products: [],
    page: 1,
    hasMore: true
  },

  onLoad() {
    this.loadProducts()
  },

  loadProducts() {
    const { page } = this.data
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
            products: [...this.data.products, ...items],
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