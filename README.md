# 眼镜产品展示系统

## 项目结构
```
eyewear-display/
├── backend/               # Flask后端
│   ├── app.py            # 主应用文件
│   ├── config.py         # 配置文件
│   ├── models.py         # 数据库模型
│   ├── requirements.txt  # Python依赖
│   └── .env.example      # 环境变量示例
└── miniprogram/          # 微信小程序前端
    ├── app.js            # 小程序入口文件
    ├── app.json          # 小程序配置
    ├── pages/            # 页面文件夹
    │   ├── index/        # 产品列表页
    │   └── product/      # 产品详情页
    └── project.config.json
```

## 后端设置

1. 安装依赖：
```bash
cd backend
pip install -r requirements.txt
```

2. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入实际的配置信息
```

3. 运行后端服务：
```bash
python app.py
```

## 微信小程序设置

1. 在微信开发者工具中导入项目：
   - 选择 `miniprogram` 目录
   - 填入自己的小程序 AppID

2. 修改服务器配置：
   - 在 `app.js` 中修改 `apiBaseUrl` 为实际的后端服务器地址

## API 接口

### 获取产品列表
```
GET /api/products?page=1&per_page=10
```

### 获取产品详情
```
GET /api/products/<frame_model>
```

## 注意事项

1. 确保数据库中的图片 token 可以正确访问
2. 配置正确的跨域设置
3. 在生产环境中使用 HTTPS
4. 确保服务器有足够的存储空间存放图片