const app = getApp()

Component({
  data: {
    selected: 0,
    color: '#666',
    selectedColor: '#E60012',
    // 三个 tab（销售或未分配用户）
    fullList: [
      {
        pagePath: 'pages/index/index',
        text: '商品',
        iconPath: '/images/index.png',
        selectedIconPath: '/images/index_sel.png'
      },
      {
        pagePath: 'pages/watchlist/index',
        text: '推荐',
        iconPath: '/images/watchlist.png',
        selectedIconPath: '/images/watchlist_sel.png'
      },
      {
        pagePath: 'pages/user/user',
        text: '我的',
        iconPath: '/images/user.png',
        selectedIconPath: '/images/user_sel.png'
      }
    ],
    // 两个 tab（已分配销售的普通用户）
    reducedList: [
      {
        pagePath: 'pages/watchlist/index',
        text: '推荐',
        iconPath: '/images/watchlist.png',
        selectedIconPath: '/images/watchlist_sel.png'
      },
      {
        pagePath: 'pages/user/user',
        text: '我的',
        iconPath: '/images/user.png',
        selectedIconPath: '/images/user_sel.png'
      }
    ],
    // 两个 tab（未分配销售的普通用户）：商品 + 我的
    customerNoSalesList: [
      {
        pagePath: 'pages/index/index',
        text: '商品',
        iconPath: '/images/index.png',
        selectedIconPath: '/images/index_sel.png'
      },
      {
        pagePath: 'pages/user/user',
        text: '我的',
        iconPath: '/images/user.png',
        selectedIconPath: '/images/user_sel.png'
      }
    ],
    // 默认先展示完整 tab，等待角色加载后再切换，避免首屏空白
    list: [
      {
        pagePath: 'pages/index/index',
        text: '商品',
        iconPath: '/images/index.png',
        selectedIconPath: '/images/index_sel.png'
      },
      {
        pagePath: 'pages/watchlist/index',
        text: '推荐',
        iconPath: '/images/watchlist.png',
        selectedIconPath: '/images/watchlist_sel.png'
      },
      {
        pagePath: 'pages/user/user',
        text: '我的',
        iconPath: '/images/user.png',
        selectedIconPath: '/images/user_sel.png'
      }
    ]
  },
  lifetimes: {
    attached() {
      // 初始化 tab 列表并根据当前页面设置选中项
      this._init()
      this._dbg('attached:init', { global: app && app.globalData })
      // 订阅角色变更，动态刷新
      if (app && app.addRoleListener) {
        this._roleCb = () => this._refreshByRole()
        app.addRoleListener(this._roleCb)
      }
    },
    detached() {
      if (this._roleCb && app && app.removeRoleListener) {
        app.removeRoleListener(this._roleCb)
      }
    }
  },
  methods: {
    _dbg(tag, data) {
      try {
        if (app && app.globalData && app.globalData.debug) {
          const oid = (app.globalData && app.globalData.openId) || ''
          const payload = (data && typeof data === 'object') ? Object.assign({}, data, { oid }) : { msg: data, oid }
          console.log('[TAB]', tag, payload)
        }
      } catch (e) {}
    },
    _init() {
      // 先用当前全局角色渲染一次，避免空白
      this._refreshByRole()
      // 若还未有角色信息，尝试预取之后再次刷新
      if (app && app.fetchAndCacheRole) {
        app.fetchAndCacheRole().finally(() => {
          this._refreshByRole()
        })
      }
    },
    _refreshByRole() {
      const isSales = !!(app && app.globalData && app.globalData.isSales)
      const hasMySales = !!(app && app.globalData && app.globalData.hasMySales)
      
      let list = this.data.fullList
      if (!isSales) {
        if (hasMySales) {
          list = this.data.reducedList
        } else {
          list = this.data.customerNoSalesList
        }
      }

      this._dbg('refreshByRole', { isSales, hasMySales, listLen: (list || []).length })
      this.setData({ list }, () => {
        this.setSelectedByRoute()
        
        // 检查当前页面是否在新的 tab 列表中，若不在则跳转到列表第一项
        const cur = this._currentRoute()
        const hasCurrent = list.some(i => i.pagePath === cur)
        if (!hasCurrent && list.length > 0) {
          const dest = '/' + list[0].pagePath
          this._dbg('autoRedirect', { from: cur, to: dest })
          wx.switchTab({ url: dest })
        }
      })
    },
    _currentRoute() {
      const pages = getCurrentPages()
      const page = pages[pages.length - 1]
      return page && page.route
    },
    setSelected(index) {
      this.setData({ selected: Number(index) || 0 })
    },
    setSelectedByRoute() {
      const route = this._currentRoute()
      const idx = (this.data.list || []).findIndex(i => i.pagePath === route)
      this._dbg('setSelectedByRoute', { route, idx, list: this.data.list })
      this.setData({ selected: idx >= 0 ? idx : 0 })
    },
    switchTab(e) {
      const index = Number(e.currentTarget.dataset.index)
      const item = (this.data.list || [])[index]
      if (!item) return
      const url = '/' + item.pagePath
      this._dbg('switchTab', { index, item })
      if (wx && wx.switchTab) {
        wx.switchTab({ url })
      }
      this.setSelected(index)
    }
  }
})
