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
    searchQuery: '',
    fieldOptions: [
      { label: '镜架型号', value: (config && config.defaultSearchField) || 'frame_model' },
      { label: '镜片大小', value: 'lens_size' },
      { label: '鼻梁宽度', value: 'nose_bridge_width' },
      { label: '镜腿长度', value: 'temple_length' },
      { label: '镜架总长', value: 'frame_total_length' },
      { label: '镜架高度', value: 'frame_height' }
      // 未来可扩展更多字段，如品牌、材料等
    ],
    fieldIndex: 0,
    placeholder: (config && config.searchPlaceholder) || '搜索镜架型号（精确匹配）',
    history: [],
  helpText: `最近搜索保留 5 条
支持按如下字段进行精确匹配搜索：
镜架型号（frame_model）：如“98044”，搜索fm98044
镜片大小（lens_size）：如“43mm”，搜索ls43
鼻梁宽度（nose_bridge_width）：如“25mm”，搜索nw25
镜腿长度（temple_length）：如“145mm”，搜索tl145
镜架总长（frame_total_length）：如“140mm”，搜索fl140
镜架高度（frame_height）：如“40mm”，搜索fh40
  `, // 可在此处自行调整文案
    // 无结果提示（可在界面展示，文案可改）
    noResult: false,
    noResultText: '未找到任何结果，请调整搜索条件后重试。',
    // 输入框键盘类型：文本/数字
    inputType: 'text',
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
        const { searchField, searchQuery, filters } = payload
        if (searchQuery) this.setData({ searchQuery })
        if (searchField) {
          const idx = this.data.fieldOptions.findIndex(o => o.value === searchField)
          if (idx >= 0) this.setData({ fieldIndex: idx }, () => this._updateInputType())
          else this._updateInputType()
        } else {
          this._updateInputType()
        }
        if (filters && typeof filters === 'object') {
          // 仅覆盖已知字段，避免污染
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

  onFieldChange(e) {
    const idx = Number(e.detail.value || 0)
    this.setData({ fieldIndex: idx }, () => this._updateInputType())
  },

  onInput(e) {
    const v = (e.detail && e.detail.value) || ''
    this.setData({ searchQuery: v })
  },

  onInputMulti(e) {
    const field = e.currentTarget.dataset.field
    const v = (e.detail && e.detail.value) || ''
    if (!field) return
    const filters = Object.assign({}, this.data.filters, { [field]: v })
    this.setData({ filters })
  },

  onConfirm() {
    const field = this.data.fieldOptions[this.data.fieldIndex].value
    const value = (this.data.searchQuery || '').trim()
    if (!value) {
      wx.showToast({ title: '请输入搜索内容', icon: 'none' })
      return
    }
    // 先校验后端是否有结果，有则返回首页并搜索；没有则停留当前页提示
    this._checkAndProceed(field, value)
  },

  onTapHistory(e) {
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
      wx.showToast({ title: '请至少填写一个条件', icon: 'none' })
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
          // 保存每个非空条件到历史
          Object.keys(params).forEach(k => this._saveHistory(k, params[k]))
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

  _checkAndProceed(field, value) {
    try {
      wx.showLoading({ title: '检查中...', mask: true })
    } catch (e) {}
    wx.request({
      url: `${app.globalData.apiBaseUrl}/products`,
      method: 'GET',
      data: {
        page: 1,
        per_page: 1,         // 仅需判断是否有结果
        search_field: field,
        search_value: value
      },
      success: (res) => {
        const ok = res && res.data && res.data.status === 'success'
        const data = ok && res.data.data
        const total = (data && (typeof data.total === 'number' ? data.total : (data.items && data.items.length))) || 0
        if (total > 0) {
          this._saveHistory(field, value)
          this._emitAndBack(field, value)
        } else {
          this.setData({ noResult: true })
          wx.showToast({ title: '没有找到匹配结果', icon: 'none' })
        }
      },
      fail: () => {
        wx.showToast({ title: '网络错误，请稍后再试', icon: 'none' })
      },
      complete: () => {
        try { wx.hideLoading() } catch (e) {}
      }
    })
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

  _updateInputType() {
    try {
      const field = this.data.fieldOptions[this.data.fieldIndex].value
      // 非型号字段使用数字键盘
      const numeric = field !== 'frame_model'
      this.setData({ inputType: numeric ? 'number' : 'text' })
    } catch (e) {
      this.setData({ inputType: 'text' })
    }
  },

  getFieldLabel(field) {
    const opt = this.data.fieldOptions.find(o => o.value === field)
    return opt ? opt.label : field
  }
})
