const app = getApp()

Component({
  data: {
    selected: 0,
    color: '#666',
    selectedColor: '#1a1a1a',
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
        text: '个人',
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
        text: '个人',
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
        text: '个人',
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
      try { if (app && app.globalData && app.globalData.debug) console.log('[TAB]', tag, data || '') } catch (e) {}
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
      const useReduced = (!isSales && hasMySales)
      const list = useReduced ? this.data.reducedList : this.data.fullList
      this._dbg('refreshByRole', { isSales, hasMySales, useReduced, listLen: (list || []).length })
      this.setData({ list }, () => {
        this.setSelectedByRoute()
        // 如果当前是 index 页面且被隐藏，则跳转到“推荐”
        const cur = this._currentRoute()
        const hasIndex = list.some(i => i.pagePath === 'pages/index/index')
        if (!hasIndex && cur === 'pages/index/index') {
          this._dbg('redirectFromIndexToWatchlist', { cur })
          wx.switchTab({ url: '/pages/watchlist/index' })
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
