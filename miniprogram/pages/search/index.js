const app = getApp()
const config = require('../../config.js')

Page({
  data: {
    // 自定义导航尺寸（与首页一致）
    statusBarHeight: 20,
    navBarHeight: 44,
    navHeight: 64,
    capsuleRightWidth: 0,
    menuHeight: 32,
    history: [],
  helpText: `最近搜索保留 5 条
支持按如下字段进行精确匹配或范围匹配：
镜架型号（frame_model）：如“98044”
镜片大小（lens_size）：如“50”或“40-45”
鼻梁宽度（nose_bridge_width）：如“18”或“16-20”
镜腿长度（temple_length）：如“145”或“140-150”
镜架总长（frame_total_length）：如“140”或“135-145”
镜架高度（frame_height）：如“42”或“40-45”
  `, // 可在此处自行调整文案
    // 无结果提示（可在界面展示，文案可改）
    noResult: false,
    noResultText: '未找到任何结果，请调整搜索条件后重试。',
    // 多字段筛选的输入值
    filters: {
      frame_model: '',
      lens_size: '',
      nose_bridge_width: '',
      temple_length: '',
      frame_total_length: '',
      frame_height: ''
    }
  },

  onLoad() {
    // 计算状态栏/胶囊尺寸，保证导航与首页对齐
    try {
      const sys = wx.getSystemInfoSync()
      const menu = wx.getMenuButtonBoundingClientRect ? wx.getMenuButtonBoundingClientRect() : null
      const statusBarHeight = sys.statusBarHeight || 20
      let navBarHeight = 44
      if (menu && menu.top && menu.height) {
        navBarHeight = (menu.top - statusBarHeight) * 2 + menu.height
      }
      const navHeight = statusBarHeight + navBarHeight
      const capsuleRightWidth = menu ? (sys.windowWidth - menu.left + 8) : 80
      const menuHeight = menu && menu.height ? menu.height : 32
      this.setData({ statusBarHeight, navBarHeight, navHeight, capsuleRightWidth, menuHeight })
    } catch (e) {}

    this._loadHistory()
    // 接收初始值（若从首页带来）
    const ec = this.getOpenerEventChannel && this.getOpenerEventChannel()
    if (ec && ec.on) {
      ec.on('init', (payload) => {
        if (!payload) return
        const filters = payload.filters
        if (filters && typeof filters === 'object') {
          const cur = this.data.filters
          this.setData({
            filters: {
              frame_model: filters.frame_model || cur.frame_model,
              lens_size: filters.lens_size || cur.lens_size,
              nose_bridge_width: filters.nose_bridge_width || cur.nose_bridge_width,
              temple_length: filters.temple_length || cur.temple_length,
              frame_total_length: filters.frame_total_length || cur.frame_total_length,
              frame_height: filters.frame_height || cur.frame_height
            }
          })
        }
      })
    }
  },

  onTapHistory(e) {
    const filters = e.currentTarget.dataset.filters
    if (filters && typeof filters === 'object') {
      // 组合搜索历史：直接回填并返回首页
      const ec = this.getOpenerEventChannel && this.getOpenerEventChannel()
      if (ec && ec.emit) {
        ec.emit('search', { filters })
      }
      wx.navigateBack({ delta: 1 })
      return
    }
    const field = e.currentTarget.dataset.field
    const value = e.currentTarget.dataset.value
    if (!value) return
    this._emitAndBack(field, value)
  },

  onClearHistory() {
    try {
      wx.removeStorageSync('search_history_v1')
    } catch (e) {}
    this.setData({ history: [] })
  },

  onCancel() {
    wx.navigateBack({ delta: 1 })
  },

  onInputMulti(e) {
    const field = e.currentTarget.dataset.field
    const v = (e.detail && e.detail.value) || ''
    if (!field) return
    const filters = Object.assign({}, this.data.filters)
    filters[field] = v
    this.setData({ filters })
  },

  _emitAndBack(field, value) {
    const ec = this.getOpenerEventChannel && this.getOpenerEventChannel()
    if (ec && ec.emit) {
      ec.emit('search', { searchField: field, searchValue: value })
    }
    wx.navigateBack({ delta: 1 })
  },

  onSearchMulti() {
    // 收集非空过滤项
    const f = this.data.filters || {}
    const params = {}
    let count = 0
    ;['frame_model','lens_size','nose_bridge_width','temple_length','frame_total_length','frame_height'].forEach(k => {
      const val = (f[k] || '').toString().trim()
      if (val !== '') { params[k] = val; count++ }
    })
    if (count === 0) {
      // 无条件，视为“查看全部”。直接清空筛选并返回。
      const ec = this.getOpenerEventChannel && this.getOpenerEventChannel()
      if (ec && ec.emit) {
        ec.emit('search', { filters: {} })
      }
      wx.navigateBack({ delta: 1 })
      return
    }
    try { wx.showLoading({ title: '检查中...', mask: true }) } catch (e) {}
    wx.request({
      url: `${app.globalData.apiBaseUrl}/products`,
      method: 'GET',
      data: Object.assign({ page: 1, per_page: 1 }, params),
      success: (res) => {
        const ok = res && res.data && res.data.status === 'success'
        const data = ok && res.data.data
        const total = (data && (typeof data.total === 'number' ? data.total : (data.items && data.items.length))) || 0
        if (total > 0) {
          // 保存为一个组合搜索历史项
          this._saveHistoryCombined(params)
          const ec = this.getOpenerEventChannel && this.getOpenerEventChannel()
          if (ec && ec.emit) {
            ec.emit('search', { filters: params })
          }
          wx.navigateBack({ delta: 1 })
        } else {
          this.setData({ noResult: true })
          wx.showToast({ title: '没有找到匹配结果', icon: 'none' })
        }
      },
      fail: () => {
        wx.showToast({ title: '网络错误，请稍后再试', icon: 'none' })
      },
      complete: () => { try { wx.hideLoading() } catch (e) {} }
    })
  },

  _normalizedFiltersObject(obj){
    // 只保留已知字段，去空值，并按固定顺序返回新对象
    const order = ['frame_model','lens_size','nose_bridge_width','temple_length','frame_total_length','frame_height']
    const out = {}
    order.forEach(k => {
      const v = (obj && obj[k] !== undefined && obj[k] !== null) ? (''+obj[k]).trim() : ''
      if (v !== '') out[k] = v
    })
    return out
  },

  _saveHistoryCombined(filters){
    try {
      const key = 'search_history_v1'
      let arr = wx.getStorageSync(key) || []
      if (!Array.isArray(arr)) arr = []
      const nf = this._normalizedFiltersObject(filters)
      // 生成去重签名
      const signature = JSON.stringify(nf)
      // 过滤掉相同组合的旧记录
      arr = arr.filter(i => {
        if (i && i.filters && typeof i.filters === 'object') {
          try { return JSON.stringify(this._normalizedFiltersObject(i.filters)) !== signature } catch (e) { return true }
        }
        // 保留单字段历史，允许并存
        return true
      })
      // 插入新纪录到顶部
      arr.unshift({ type: 'multi', filters: nf })
      if (arr.length > 5) arr = arr.slice(0, 5)
      wx.setStorageSync(key, arr)
      this.setData({ history: arr })
    } catch (e) {}
  },

  _loadHistory() {
    try {
      const arr = wx.getStorageSync('search_history_v1') || []
      this.setData({ history: Array.isArray(arr) ? arr : [] })
    } catch (e) {}
  },

  _saveHistory(field, value) {
    try {
      const key = 'search_history_v1'
      let arr = wx.getStorageSync(key) || []
      if (!Array.isArray(arr)) arr = []
      // 去重（按 field+value），并将当前项置顶
      arr = arr.filter(i => !(i.field === field && i.value === value))
      arr.unshift({ field, value })
      // 限制前 5 条
      if (arr.length > 5) arr = arr.slice(0, 5)
      wx.setStorageSync(key, arr)
      this.setData({ history: arr })
    } catch (e) {}
  },

  
})
