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
    menuTop: 0, // 胶囊按钮的 Top 值，用于对齐
    history: [],
  helpText: `最近搜索保留 5 条
支持按如下字段进行精确匹配或范围匹配：
镜架型号（文本，需精确匹配）：如“98044”或“T18981”
镜片大小（数字，范围35≤x≤70）：如“50”或“40-45”
鼻梁宽度（数字，范围10≤x≤35）：如“18”或“16-20”
镜腿长度（数字，范围120≤x≤170）：如“145”或“140-150”
镜架总长（数字，范围100≤x≤160）：如“140”或“135-145”
镜架高度（数字，范围20≤x≤60）：如“42”或“40-45”
镜架材料（多选）：如“TR,钛”表示“TR”或者“钛”
重量（数字，范围3≤x≤50）：如“20”或“18-22”
售价（数字，范围50≤x≤500）：如“199”或“100-300”
品牌信息（文本）：仅在“所属品牌”字段中模糊匹配
  `, // 可在此处自行调整文案
    // 无结果提示（可在界面展示，文案可改）
    noResult: false,
    noResultText: '未找到任何结果，请调整搜索条件后重试。',
    // 多字段筛选的输入值
    // 固定可选材质标签（供前端复选显示）
    materialOptions: ['TR','B钛','钛','纯钛','合金','板材','金胶','塑钢'],
    selectedMaterials: [],
    selectedMaterialMap: {},
    filters: {
      frame_model: '',
      lens_size: '',
      nose_bridge_width: '',
      temple_length: '',
      frame_total_length: '',
      frame_height: '',
      weight: '',
      price: '',
      brand_info: ''
    },
    // 字段级错误提示（仅数值字段）
    errors: {
      lens_size: '',
      nose_bridge_width: '',
      temple_length: '',
      frame_total_length: '',
      frame_height: '',
      weight: '',
      price: ''
    },
    focusedField: ''
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
      const menuTop = menu && menu.top ? menu.top : (statusBarHeight + (navBarHeight - menuHeight) / 2)
      this.setData({ statusBarHeight, navBarHeight, navHeight, capsuleRightWidth, menuHeight, menuTop })
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
          // 反推已选材质标签
          const matStr = (filters.frame_material || cur.frame_material || '')
          const selectedMaterials = matStr ? matStr.split(/[,，|]+/).map(s => (s||'').trim()).filter(Boolean) : []
          const selectedMaterialMap = {}
          selectedMaterials.forEach(t => { selectedMaterialMap[t] = true })
          this.setData({
            filters: {
              frame_model: filters.frame_model || cur.frame_model,
              lens_size: filters.lens_size || cur.lens_size,
              nose_bridge_width: filters.nose_bridge_width || cur.nose_bridge_width,
              temple_length: filters.temple_length || cur.temple_length,
              frame_total_length: filters.frame_total_length || cur.frame_total_length,
              frame_height: filters.frame_height || cur.frame_height,
              weight: filters.weight || cur.weight,
              price: filters.price || cur.price,
              brand_info: filters.brand_info || cur.brand_info,
              frame_material: matStr
            },
            selectedMaterials,
            selectedMaterialMap
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

  onResetMulti() {
    this.setData({
      filters: {
        frame_model: '',
        lens_size: '',
        nose_bridge_width: '',
        temple_length: '',
        frame_total_length: '',
        frame_height: '',
        weight: '',
        price: '',
        brand_info: '',
        frame_material: ''
      },
      selectedMaterials: [],
      selectedMaterialMap: {},
      errors: {
        lens_size: '',
        nose_bridge_width: '',
        temple_length: '',
        frame_total_length: '',
        frame_height: '',
        weight: '',
        price: ''
      },
      focusedField: ''
    })
  },

  onFocus(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ focusedField: field })
  },

  onBlur(e) {
    this.setData({ focusedField: '' })
  },

  onInputMulti(e) {
    const field = e.currentTarget.dataset.field
    const v = (e.detail && e.detail.value) || ''
    if (!field) return
    const filters = Object.assign({}, this.data.filters)
    const errors = Object.assign({}, this.data.errors)
    const norm = this._normalizeValue(v)
    filters[field] = norm
    // 仅对数值字段做校验
    if (this._isNumericField(field)) {
      const check = this._validateNumericOrRange(norm)
      errors[field] = check.ok || norm === '' ? '' : '格式错误：请输入数字或范围（如 40 或 40-45）'
    }
    this.setData({ filters, errors })
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
    // 搜索前进行一次集中校验
    const errors = Object.assign({}, this.data.errors)
    let firstErrorField = ''
    ;['frame_model','lens_size','nose_bridge_width','temple_length','frame_total_length','frame_height','weight','price','brand_info'].forEach(k => {
      const val = (f[k] || '').toString().trim()
      if (this._isNumericField(k)) {
        const chk = this._validateNumericOrRange(val)
        if (!chk.ok && val !== '') {
          errors[k] = '格式错误：请输入数字或范围（如 40 或 40-45）'
          if (!firstErrorField) firstErrorField = k
        } else {
          errors[k] = ''
        }
      }
      if (val !== '') { params[k] = val; count++ }
    })
    // 材质复选：将选中的标签组合到 frame_material（逗号分隔）
    if (this.data.selectedMaterials && this.data.selectedMaterials.length) {
      params.frame_material = this.data.selectedMaterials.join(',')
      count++
    }
    if (firstErrorField) {
      this.setData({ errors })
      wx.showToast({ title: '请修正红色字段的格式', icon: 'none' })
      return
    }
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

  // ===== 工具方法 =====
  _isNumericField(field) {
    return field === 'lens_size' || field === 'nose_bridge_width' || field === 'temple_length' || field === 'frame_total_length' || field === 'frame_height' || field === 'weight' || field === 'price'
  },
  _normalizeValue(v){
    if (v === undefined || v === null) return ''
    const s = String(v).trim()
    if (!s) return ''
    // 统一中文破折号为半角连字符
    return s.replace(/[－—–]/g, '-')
  },
  _validateNumericOrRange(s){
    if (!s) return { ok: true }
    const str = String(s)
    // 单值：整数或小数
    const numRe = /^[+-]?\d+(?:\.\d+)?$/
    if (numRe.test(str)) return { ok: true }
    // 范围：a-b，中间可有空格；a、b 都是数字
    const rangeRe = /^\s*([+-]?\d+(?:\.\d+)?)\s*-\s*([+-]?\d+(?:\.\d+)?)\s*$/
    const m = str.match(rangeRe)
    if (m) {
      // 合法范围，顺序不强制，后端会再矫正
      return { ok: true }
    }
    return { ok: false, msg: 'invalid' }
  },

  _normalizedFiltersObject(obj){
    // 只保留已知字段，去空值，并按固定顺序返回新对象
  const order = ['frame_model','lens_size','nose_bridge_width','temple_length','frame_total_length','frame_height','weight','price','brand_info','frame_material']
    const out = {}
    order.forEach(k => {
      const v = (obj && obj[k] !== undefined && obj[k] !== null) ? (''+obj[k]).trim() : ''
      if (v !== '') out[k] = v
    })
    return out
  },

  // ===== 材质标签选择 =====
  toggleMaterial(e){
    const v = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.value) || ''
    if (!v) return
    const sel = (this.data.selectedMaterials || []).slice()
    const map = Object.assign({}, this.data.selectedMaterialMap || {})
    const idx = sel.indexOf(v)
    if (idx >= 0) {
      sel.splice(idx, 1)
      delete map[v]
    } else {
      sel.push(v)
      map[v] = true
    }
    const filters = Object.assign({}, this.data.filters)
    filters.frame_material = sel.join(',')
    this.setData({ selectedMaterials: sel, selectedMaterialMap: map, filters })
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
