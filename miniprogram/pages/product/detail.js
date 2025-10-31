const app = getApp()

Page({
  data: {
    product: null
  },

  onLoad(options) {
    const { model } = options
    this.loadProduct(model)
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