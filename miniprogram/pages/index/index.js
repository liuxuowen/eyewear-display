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
    // 同步选中自定义 tabBar
    try {
      const tb = this.getTabBar && this.getTabBar()
      if (tb && tb.setSelectedByRoute) tb.setSelectedByRoute()
    } catch (e) {}
    if (app.globalData.openId) {
      track(app.globalData.openId)
      this._updateKfSessionFrom()
      // 每次显示首页时强制刷新收藏状态（解决在收藏页取消后返回仍显示“已收藏”的问题）
      this._loadFavoriteIds()
      this._loadUserRole()
      this._applyPendingSkus()
      this._applyPendingSales()
      this._applyPendingReferrer()
    } else if (app.loginIfNeeded) {
      app.loginIfNeeded()
        .then((oid) => {
          track(oid)
          this._updateKfSessionFrom()
          this._loadFavoriteIds()
          this._loadUserRole()
          this._applyPendingSkus()
          this._applyPendingSales()
          this._applyPendingReferrer()
        })
        .catch(() => {})
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
    // 顶部搜索框显示文本（单字段或组合展示）
    searchDisplay: '',
    // 当前用户已收藏的型号集合（用于按钮状态）
    favoriteIds: {},
    // 角色与分享选择
    isSales: false,
  hasMySales: false,
    selecting: false,
    selectedMap: {},
    selectedCount: 0,
    // 分享落地待加入收藏的SKU
    pendingSkus: null,
    // 分享落地待关联的销售open_id
    pendingSalesOpenId: '',
    // 分享落地待绑定的推荐人 open_id
    pendingReferrerOpenId: '',
    // 是否在处理完分享落地后跳转收藏页
    autoGoWatchlist: false,
    // 客服会话来源参数
    kfSessionFrom: '',
    // 自定义导航栏尺寸
    statusBarHeight: 20,
    navBarHeight: 44,
    navHeight: 64,
    capsuleRightWidth: 0,
    menuHeight: 32
  },
  onLoad(options) {
    // 开启/关闭调试：?debug=1 或 ?debug=0
    try {
      if (options && (options.debug === '1' || options.debug === 'true')) {
        app.setDebug && app.setDebug(true)
        wx.showToast({ title: 'DEBUG ON', icon: 'none' })
      } else if (options && (options.debug === '0' || options.debug === 'false')) {
        app.setDebug && app.setDebug(false)
        wx.showToast({ title: 'DEBUG OFF', icon: 'none' })
      }
      app._log && app._log('index:onLoad:options', options)
    } catch (e) {}
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
    this._updateSearchDisplay()
    this._loadFavoriteIds()
    this.loadProducts()
    this._updateKfSessionFrom()
    // 处理分享落地参数（如 ?skus=a,b,c&sid=<sales_open_id>）
    if (options) {
      if (options.skus) {
        try {
          const raw = decodeURIComponent(options.skus)
          const list = raw.split(',').map(s => (s||'').trim()).filter(Boolean)
          if (list && list.length) {
            this.setData({ pendingSkus: list, autoGoWatchlist: true })
          }
        } catch (e) {}
      }
      if (options.sid) {
        try {
          const sid = decodeURIComponent(options.sid)
          if (sid) this.setData({ pendingSalesOpenId: sid })
        } catch (e) {}
      }
      // 推荐关系：?ref=<referrer_open_id> 或 ?rid=<referrer_open_id>
      if (options.ref || options.rid) {
        try {
          const rid = decodeURIComponent(options.ref || options.rid)
          if (rid) this.setData({ pendingReferrerOpenId: rid })
        } catch (e) {}
      }
    }
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
          const newItems = (items || []).map(it => this._withHighlights(it))
          this.setData({
            products: this.data.products.concat(newItems),
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
      this._loadFavoriteIds()
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

  clearSearch() {
    this.setData({
      filters: null,
      searchQuery: ''
    }, () => {
      this._updateSearchDisplay()
      this._doSearch()
    })
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
            this.setData({ filters, searchQuery: '' }, () => {
              this._updateSearchDisplay()
              this._doSearch()
            })
          } else {
            this.setData({
              filters: null,
              searchField: searchField || this.data.searchField,
              searchQuery: searchValue || ''
            }, () => {
              this._updateSearchDisplay()
              this._doSearch()
            })
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
  ,
  _withHighlights(item) {
    const filters = this.data.filters
    const isMulti = filters && typeof filters === 'object'
    const sf = this.data.searchField
    const sq = (this.data.searchQuery || '').trim()

    const hl = {}
    const v = (x) => (x === undefined || x === null) ? '' : ('' + x)
    // 材质标签（由后端存储的 frame_material 通过 '+' 拆分）
    const mats = v(item.frame_material).split('+').map(s => s.trim()).filter(Boolean)
    const cleanSentinel = (s) => {
      const t = (s || '').toString().trim()
      if (!t) return ''
      return /^(none|null|undefined|nan)$/i.test(t) ? '' : t
    }
    const brandText = cleanSentinel(item.brand)
    const notesText = cleanSentinel(item.notes)

    // 帮助函数：子串高亮
    const highlightSubstring = (text, kw) => {
      const src = v(text)
      const key = v(kw)
      if (!src) return [{ text: src, highlight: false }]
      if (!key) return [{ text: src, highlight: false }]
      const idx = src.indexOf(key)
      if (idx < 0) return [{ text: src, highlight: false }]
      const parts = []
      if (idx > 0) parts.push({ text: src.slice(0, idx), highlight: false })
      parts.push({ text: src.slice(idx, idx + key.length), highlight: true })
      if (idx + key.length < src.length) parts.push({ text: src.slice(idx + key.length), highlight: false })
      return parts
    }

    // 帮助函数：整段高亮
    const highlightAll = (text) => [{ text: v(text), highlight: true }]

    // 判断数值是否在范围内（字符串，可能是 a-b 或单值）
    const inRange = (num, expr) => {
      if (num === undefined || num === null) return false
      const n = Number(num)
      if (!expr) return false
      const s = ('' + expr).replace(/[－—–]/g, '-')
      const m = s.match(/^\s*([+-]?\d+(?:\.\d+)?)\s*-\s*([+-]?\d+(?:\.\d+)?)\s*$/)
      if (m) {
        const a = Number(m[1]); const b = Number(m[2])
        if (isNaN(a) || isNaN(b)) return false
        const lo = Math.min(a, b), hi = Math.max(a, b)
        return n >= lo && n <= hi
      }
      const single = Number(s)
      if (isNaN(single)) return false
      // 允许极小误差
      return Math.abs(n - single) < 1e-4
    }

    // 计算各字段的高亮片段
  const otherText = `${brandText} ${notesText}`.trim()
    if (isMulti) {
      // frame_model：按子串高亮
      if (filters.frame_model) {
        hl.frame_model = highlightSubstring(item.frame_model, filters.frame_model)
      }
      // 数值字段：若为单值则子串高亮；若为范围且命中则整段高亮
      const handleNumeric = (field, displayVal, rawVal) => {
        const expr = filters[field]
        if (!expr) return
        const exprStr = ('' + expr)
        const isRange = /-/.test(exprStr)
        if (isRange) {
          if (inRange(rawVal, exprStr)) {
            hl[field] = highlightAll(displayVal)
          }
        } else {
          hl[field] = highlightSubstring(displayVal, exprStr)
        }
      }
      handleNumeric('lens_size', v(item.lens_size), item.lens_size)
      handleNumeric('nose_bridge_width', v(item.nose_bridge_width), item.nose_bridge_width)
      handleNumeric('temple_length', v(item.temple_length), item.temple_length)
      handleNumeric('frame_total_length', v(item.frame_total_length), item.frame_total_length)
      handleNumeric('frame_height', v(item.frame_height), item.frame_height)
      handleNumeric('weight', v(item.weight), item.weight)
      handleNumeric('price', v(item.price), item.price)
      if (filters.other_info) {
        // 旧的“其他信息”字段：现在仅对品牌做高亮提示（备注不再在此行高亮）
        hl.brand = highlightSubstring(brandText, filters.other_info)
      }
      if (filters.brand_info) {
        // 新的“品牌信息”字段：仅对品牌做高亮
        hl.brand = highlightSubstring(brandText, filters.brand_info)
      }
      // 材质标签高亮（多选）
      if (filters.frame_material) {
        const sel = ('' + filters.frame_material).split(/[，,|]+/).map(s => s.trim()).filter(Boolean)
        const set = {}
        sel.forEach(t => { set[t] = true })
        hl.material_tokens = mats.map(t => ({ text: t, highlight: !!set[t] }))
      }
    } else if (sq) {
      // 单字段
      if (sf === 'frame_model') {
        hl.frame_model = highlightSubstring(item.frame_model, sq)
      } else if (sf === 'lens_size') {
        hl.lens_size = highlightSubstring(v(item.lens_size), sq)
      } else if (sf === 'nose_bridge_width') {
        hl.nose_bridge_width = highlightSubstring(v(item.nose_bridge_width), sq)
      } else if (sf === 'temple_length') {
        hl.temple_length = highlightSubstring(v(item.temple_length), sq)
      } else if (sf === 'frame_total_length') {
        hl.frame_total_length = highlightSubstring(v(item.frame_total_length), sq)
      } else if (sf === 'frame_height') {
        hl.frame_height = highlightSubstring(v(item.frame_height), sq)
      } else if (sf === 'weight') {
        hl.weight = highlightSubstring(v(item.weight), sq)
      } else if (sf === 'price') {
        hl.price = highlightSubstring(v(item.price), sq)
      } else if (sf === 'other_info') {
        // 单字段“其他信息”搜索：此处仅对品牌高亮
        hl.brand = highlightSubstring(brandText, sq)
      } else if (sf === 'brand_info') {
        // 单字段“品牌信息”搜索：仅品牌高亮
        hl.brand = highlightSubstring(brandText, sq)
      } else if (sf === 'frame_material') {
        const sel = ('' + sq).split(/[，,|]+/).map(s => s.trim()).filter(Boolean)
        const set = {}
        sel.forEach(t => { set[t] = true })
        hl.material_tokens = mats.map(t => ({ text: t, highlight: !!set[t] }))
      }
    }

  return Object.assign({}, item, { hl, mats, brand_text: brandText, notes_text: notesText })
  },
  _loadUserRole() {
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) return
    wx.request({
      url: `${app.globalData.apiBaseUrl}/users/role`,
      method: 'GET',
      data: { open_id: oid },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const role = res.data.data && res.data.data.role
          const hasMySales = !!(res.data.data && (res.data.data.has_my_sales || res.data.data.my_sales_open_id))
          const isSales = role === 'sales'
          this.setData({ isSales, hasMySales })
          // 写入全局并通知（供自定义 tabBar 动态隐藏“商品”）
          if (app && app._setRoleFromServer) {
            app._setRoleFromServer(res.data.data)
          }
          // 若为普通用户且已分配销售，则跳转至“收藏/推荐”页，隐藏首页商品列表
          if (!isSales && hasMySales) {
            this._goToRecommendations()
          }
        }
      }
    })
  },
  _goToRecommendations() {
    try {
      if (wx.switchTab) {
        wx.switchTab({ url: '/pages/watchlist/index' })
      } else {
        wx.navigateTo({ url: '/pages/watchlist/index' })
      }
    } catch (e) {}
  },
  _applyPendingSkus() {
    const list = this.data.pendingSkus
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!list || !list.length || !oid) return
    this.setData({ pendingSkus: null })
    // 销售点击打包卡片：需要“重置收藏”后再加入；普通用户保持原逻辑
    const isSales = !!(((getApp().globalData && getApp().globalData.isSales) || false) || this.data.isSales)
    wx.request({
      url: `${app.globalData.apiBaseUrl}/favorites/batch`,
      method: 'POST',
      data: { open_id: oid, frame_models: list.slice(0, 50), reset: isSales },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const added = (res.data.data && res.data.data.added) || 0
          const didReset = !!(res.data.data && res.data.data.reset)
          if (didReset || added > 0) {
            this._loadFavoriteIds()
            const msg = didReset ? `已重置收藏并加入${added}个` : `已加入收藏${added}个`
            wx.showToast({ title: msg, icon: 'success' })
          }
          // 处理跳转逻辑（避免重复）
          if (this.data.autoGoWatchlist) {
            this.setData({ autoGoWatchlist: false })
            wx.switchTab ? wx.switchTab({ url: '/pages/watchlist/index' }) : wx.navigateTo({ url: '/pages/watchlist/index' })
          }
        }
      }
    })
  },
  _applyPendingSales() {
    const sid = (this.data.pendingSalesOpenId || '').trim()
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!sid || !oid) return
    this.setData({ pendingSalesOpenId: '' })
    wx.request({
      url: `${app.globalData.apiBaseUrl}/users/mysales`,
      method: 'POST',
      data: { open_id: oid, my_sales_open_id: sid },
      success: (res) => {
        // 成功或幂等：刷新角色缓存以便自定义 tabBar 立刻生效
        if (app && app.fetchAndCacheRole) {
          app.fetchAndCacheRole()
            .then(() => {
              const isSales = !!(app.globalData && app.globalData.isSales)
              const hasMySales = !!(app.globalData && app.globalData.hasMySales)
              if (!isSales && hasMySales) {
                this._goToRecommendations()
              }
            })
            .catch(() => {})
        }
      }
    })
  },
  _applyPendingReferrer() {
    const rid = (this.data.pendingReferrerOpenId || '').trim()
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!rid || !oid) return
    if (rid === oid) { this.setData({ pendingReferrerOpenId: '' }); return }
    this.setData({ pendingReferrerOpenId: '' })
    wx.request({
      url: `${app.globalData.apiBaseUrl}/users/referrer`,
      method: 'POST',
      data: { open_id: oid, referrer_open_id: rid },
      success: () => { /* 幂等或已设置均静默 */ },
      fail: () => { /* 忽略错误 */ }
    })
  },
  _loadFavoriteIds() {
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) return
    wx.request({
      url: `${app.globalData.apiBaseUrl}/favorites/ids`,
      method: 'GET',
      data: { open_id: oid },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const arr = ((res.data.data && res.data.data.items) || [])
          const map = {}
          arr.forEach(m => { map[m] = true })
          this.setData({ favoriteIds: map })
        }
      }
    })
  },
  toggleFavorite(e) {
    const model = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.model) || ''
    if (!model) return
    const oid = (getApp().globalData && getApp().globalData.openId) || ''
    if (!oid) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    const isFav = !!(this.data.favoriteIds && this.data.favoriteIds[model])
    if (isFav) {
      // 已收藏 -> 取消收藏
      wx.request({
        url: `${app.globalData.apiBaseUrl}/favorites`,
        method: 'DELETE',
        data: { open_id: oid, frame_model: model },
        success: (res) => {
          if (res.data && res.data.status === 'success') {
            const m = Object.assign({}, this.data.favoriteIds)
            delete m[model]
            this.setData({ favoriteIds: m })
            wx.showToast({ title: '已取消收藏', icon: 'success' })
          } else {
            wx.showToast({ title: (res.data && res.data.message) || '取消失败', icon: 'none' })
          }
        },
        fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
      })
    } else {
      // 未收藏 -> 添加收藏（幂等）
      wx.request({
        url: `${app.globalData.apiBaseUrl}/favorites`,
        method: 'POST',
        data: { open_id: oid, frame_model: model },
        success: (res) => {
          if (res.data && res.data.status === 'success') {
            const m = Object.assign({}, this.data.favoriteIds)
            m[model] = true
            this.setData({ favoriteIds: m })
            wx.showToast({ title: '已收藏', icon: 'success' })
          } else {
            wx.showToast({ title: (res.data && res.data.message) || '收藏失败', icon: 'none' })
          }
        },
        fail: () => wx.showToast({ title: '网络错误', icon: 'none' })
      })
    }
  },
  _updateSearchDisplay() {
    const filters = this.data.filters
    if (filters && typeof filters === 'object') {
      const text = this._formatFiltersDisplay(filters)
      this.setData({ searchDisplay: text })
    } else {
      this.setData({ searchDisplay: this.data.searchQuery || '' })
    }
  },
  // 销售选择与分享
  toggleSelecting() {
    if (!this.data.isSales) return
    const on = !this.data.selecting
    this.setData({ selecting: on })
    if (!on) this.setData({ selectedMap: {}, selectedCount: 0 })
  },
  toggleSelectItem(e) {
    if (!this.data.isSales || !this.data.selecting) return
    const model = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.model) || ''
    if (!model) return
    const map = Object.assign({}, this.data.selectedMap)
    if (map[model]) {
      delete map[model]
    } else {
      const cnt = this.data.selectedCount || 0
      if (cnt >= 10) {
        wx.showToast({ title: '最多选择10个', icon: 'none' })
        return
      }
      map[model] = true
    }
    const count = Object.keys(map).length
    this.setData({ selectedMap: map, selectedCount: count })
  },
  onShareAppMessage() {
    // 生成分享路径（若为销售选择打包）
    const isSales = !!this.data.isSales
    const selecting = !!this.data.selecting
    const selectedCount = Number(this.data.selectedCount || 0)
    const selectedMap = this.data.selectedMap || {}

    let path = '/pages/index/index'
    if (isSales && selecting && selectedCount > 0) {
      const skus = Object.keys(selectedMap)
      const enc = encodeURIComponent(skus.join(','))
      const sid = (getApp().globalData && getApp().globalData.openId) || ''
      const sidParam = sid ? `&sid=${encodeURIComponent(sid)}` : ''
      path = `/pages/index/index?skus=${enc}${sidParam}`
    }

    // 需求：完成打包转发后回到商品首页（退出选择模式）
    // 在触发分享时立即退出选择模式并清空已选，避免停留在选择态
    if (isSales && selecting) {
      try {
        const fn = () => this.setData({ selecting: false, selectedMap: {}, selectedCount: 0 })
        // 使用 setTimeout 避免与分享流程的同步返回竞争
        setTimeout(fn, 0)
      } catch (e) {}
    }

    return { title: selectedCount > 0 ? `推荐${selectedCount}款镜架` : '精品镜架推荐', path }
  },
  _formatFiltersDisplay(filters) {
    const order = ['frame_model','lens_size','nose_bridge_width','temple_length','frame_total_length','frame_height','weight','price','brand_info','other_info','frame_material']
    const labels = {
      frame_model: '型号',
      lens_size: '镜片',
      nose_bridge_width: '鼻梁',
      temple_length: '镜腿',
      frame_total_length: '总长',
      frame_height: '高度',
      weight: '重量',
      price: '售价',
      brand_info: '品牌',
      other_info: '其他',
      frame_material: '材质'
    }
    const parts = []
    order.forEach(k => {
      const v = filters && filters[k]
      if (v !== undefined && v !== null && (''+v).trim() !== '') {
        parts.push(`${labels[k]||k}：${v}`)
      }
    })
    return parts.join('；')
  },
  // 更新客服会话来源参数，便于在客服后台识别来源
  _updateKfSessionFrom() {
    try {
      const oid = (getApp().globalData && getApp().globalData.openId) || ''
      const now = new Date()
      const mm = String(now.getMonth() + 1).padStart(2, '0')
      const dd = String(now.getDate()).padStart(2, '0')
      const HH = String(now.getHours()).padStart(2, '0')
      const MM = String(now.getMinutes()).padStart(2, '0')
      // t:MM/DD-HH:MM（例如 11/04-14:23）
      const t = `${mm}/${dd}-${HH}:${MM}`

      const sanitize = (s) => {
        const x = (s || '').toString().replace(/[|]/g, '')
        // 控制长度，避免 session-from 过长（微信建议上限较短）
        return x.length > 8 ? x.slice(0, 8) : x
      }

      const apply = (salesName, refName) => {
        const sal = sanitize(salesName || '自然')
        const ref = sanitize(refName || '自然')
        const s = `sal:${sal}|ref:${ref}|t:${t}`
        this.setData({ kfSessionFrom: s })
      }

      if (!oid) {
        // 未登录：先填充默认
        apply('自然', '自然')
        return
      }
      // 从后端查询上下文（推荐人昵称 + 推荐人的销售姓名）
      wx.request({
        url: `${app.globalData.apiBaseUrl}/kf/context`,
        method: 'GET',
        data: { open_id: oid },
        success: (res) => {
          if (res && res.data && res.data.status === 'success' && res.data.data) {
            const salesName = res.data.data.sales_name || '自然'
            const refName = res.data.data.referrer_nickname || '自然'
            apply(salesName, refName)
          } else {
            apply('自然', '自然')
          }
        },
        fail: () => apply('自然', '自然')
      })
    } catch (e) {
      this.setData({ kfSessionFrom: 'sal:自然|ref:自然|t:0000-0000' })
    }
  }
})