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
    searchField: (config && config.defaultSearchField) || 'frame_model',
    // 多字段过滤条件（可为空对象/空值表示未启用）
    filters: null,
    // 自定义导航栏尺寸
    statusBarHeight: 20,
    navBarHeight: 44,
    navHeight: 64,
    capsuleRightWidth: 0,
    menuHeight: 32
  },

  onLoad() {
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
      const capsuleRightWidth = menu ? (sys.windowWidth - menu.left + 8) : 80
      const menuHeight = menu && menu.height ? menu.height : 32
      this.setData({ statusBarHeight, navBarHeight, navHeight, capsuleRightWidth, menuHeight })
    } catch (e) {}
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
        const filters = this.data.filters
        if (filters && typeof filters === 'object') {
          // 传递全部非空过滤项
          Object.keys(filters).forEach(k => {
            const val = (filters[k] || '').toString().trim()
            if (val !== '') d[k] = val
          })
        } else if (q) {
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

  // 自定义搜索框事件
  onSearchInput(e) {
    const v = (e.detail && e.detail.value) || ''
    this.setData({ searchQuery: v })
  },
  onSearchConfirm() {
    this.openSearchPage()
  },
  onSearchTap() {
    this.openSearchPage()
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
  },

  openSearchPage() {
    wx.navigateTo({
      url: '/pages/search/index',
      events: {
        search: (payload) => {
          if (!payload) return
          const { searchField, searchValue, filters } = payload
          if (filters && typeof filters === 'object') {
            this.setData({ filters, searchQuery: '' }, () => this._doSearch())
          } else {
            this.setData({
              filters: null,
              searchField: searchField || this.data.searchField,
              searchQuery: searchValue || ''
            }, () => this._doSearch())
          }
        }
      },
      success: (res) => {
        if (res && res.eventChannel && res.eventChannel.emit) {
          res.eventChannel.emit('init', { searchField: this.data.searchField, searchQuery: this.data.searchQuery, filters: this.data.filters })
        }
      }
    })
  }
})