const app = getApp()

Page({
  data: {
    product: null,
    model: '',
    currentImageIndex: 0
  },

  onSwiperChange(e) {
    this.setData({ currentImageIndex: e.detail.current })
  },

  onThumbnailTap(e) {
    const index = e.currentTarget.dataset.index
    this.setData({ currentImageIndex: index })
  },

  onLoad(options) {
    const { model } = options
    this.setData({ model: model || '' })
    this.loadProduct(model)

    // Calculate nav height
    try {
      const sys = wx.getSystemInfoSync()
      const menu = wx.getMenuButtonBoundingClientRect ? wx.getMenuButtonBoundingClientRect() : null
      const statusBarHeight = sys.statusBarHeight || 20
      let navBarHeight = 44
      if (menu && menu.top && menu.height) {
        navBarHeight = (menu.top - statusBarHeight) * 2 + menu.height
      }
      // Extend nav height by 20rpx (approx 10px)
      const navHeight = statusBarHeight + navBarHeight + 10
      this.setData({ statusBarHeight, navBarHeight, navHeight })
    } catch (e) {}
  },

  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    } else {
      wx.switchTab({ url: '/pages/index/index' });
    }
  },

  loadProduct(model) {
    wx.showLoading({
      title: '加载中...'
    })

    wx.request({
      url: `${app.globalData.apiBaseUrl}/products/${model}`,
      success: (res) => {
        if (res.data.status === 'success') {
          this.setData({
            product: res.data.data
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
        wx.hideLoading()
      }
    })
  },

  onShow() {
    const pagePath = '/pages/product/detail' + (this.data.model ? `?model=${this.data.model}` : '')
    const track = (oid) => {
      if (!oid) return
      wx.request({
        url: `${app.globalData.apiBaseUrl}/analytics/pageview`,
        method: 'POST',
        data: { open_id: oid, page: pagePath }
      })
    }
    if (app.globalData.openId) {
      track(app.globalData.openId)
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded().then(track).catch(() => {})
    }
  },

  previewImage(e) {
    const { current } = e.currentTarget.dataset || {}
    const { images } = this.data.product || {}
    if (!images || images.length === 0) return
    wx.previewImage({
      current: current || images[0],
      urls: images
    })
  }
})