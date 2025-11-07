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

## 部署（Nginx + HTTPS）

以下为推荐的生产部署方式（以 Debian/Ubuntu 服务器为例，域名以 yimuliaoran.top 为例）：

- 后端进程
   - 在服务器上准备 Python 环境并安装 `backend/requirements.txt`。
   - 复制 `backend/.env.production` 到服务器 `backend/.env`，并设定：
      - `APP_ENV=production`
      - `FORCE_HTTPS=1`
      - `JWT_SECRET_KEY` 为强随机值（必填）
      - `DATABASE_URL` 为你的数据库连接串
      - `IMAGE_SAVE_DIR` 指向图片目录（例如 `/var/www/resource/products_img`）
      - `IMAGE_URL_PREFIX=https://yimuliaoran.top/static/images/`（与 Nginx 静态映射一致，改为你的域名）
   - 使用 `gunicorn` 或 `waitress` 启动（参考 `scripts/backend.service.example` 或 `scripts/restart-backend.sh`）。

- Nginx 反向代理与证书
   - 若首次配置，可在服务器上执行脚本一键安装与签发证书：
      - `scripts/setup-nginx-https.sh`（需要 root，需事先将域名解析到该服务器）
   - 或手动参考 `scripts/nginx-https.conf.example` 完成以下要点：
      - 80 端口全量跳转到 HTTPS
      - 443 端口 `location /api/` 反代到后端（默认 `http://127.0.0.1:5000`，如后端监听 8080 则改为 8080）
      - `location /static/images/` 使用 `alias /var/www/resource/products_img/;` 直接由 Nginx 下发图片
      - 证书路径由 certbot 自动管理：`/etc/letsencrypt/live/<your-domain>/`

- 验证
   - 打开 `https://yimuliaoran.top/healthz` 应返回 `{"status":"ok"}`
   - 打开 `https://yimuliaoran.top/api/products` 应返回 JSON 列表
   - 图片链接应为 HTTPS，形如 `https://yimuliaoran.top/static/images/...`

- 微信小程序后台
   - 将 `https://yimuliaoran.top` 添加到 “request 合法域名”。
   - 重新编译/预览并在真机测试。

- 证书自动续期
   - Certbot 会自动安装定时任务。
   - 可在服务器执行一次演练：`certbot renew --dry-run`（需 root）。

更多细节与可选参数见 `scripts/` 目录中的示例与脚本注释。

## 测试环境（Staging）部署

目标：在同一台服务器或另一台服务器上，提供与生产相同的后端功能，但独立的域名、数据库、图片目录与证书。

推荐做法：使用二级域名，例如 `test.yimuliaoran.top`（或 `api-test.your-domain.com`）。

1) 准备后端实例
- 拷贝 `backend/.env.staging` 到测试机 `backend/.env` 并填写：
   - `APP_ENV=staging`、`FORCE_HTTPS=1`
   - 独立的 `DATABASE_URL`（避免污染生产数据）
   - 独立的图片目录：`IMAGE_SAVE_DIR=/var/www/resource/products_img_test`
   - `IMAGE_URL_PREFIX=https://test.your-domain.com/static/images/`（换成你的测试域名）
   - 独立的 `JWT_SECRET_KEY`
- 启动方式同生产，可用不同端口（例如 5001/8081）。参考 `scripts/backend.service.example`：
   - 复制一份为 `eyewear-backend-staging.service`，修改 `PORT=5001` 等环境变量。

2) Nginx + 证书
- 确保测试域名已解析到服务器公网 IP。
- 用脚本一键配置（Debian/Ubuntu）：
   ```bash
   sudo DOMAIN=test.your-domain.com EMAIL=admin@your-domain.com BACKEND_PORT=5001 STATIC_IMAGES_DIR=/var/www/resource/products_img_test SITE_NAME=eyewear-staging \
      ./scripts/setup-nginx-https.sh
   ```
- 或参照 `scripts/nginx-https.conf.example` 新建一个 `eyewear-staging.conf`：
   - `server_name test.your-domain.com;`
   - `location /api/ { proxy_pass http://127.0.0.1:5001; }`
   - `location /static/images/ { alias /var/www/resource/products_img_test/; }`
   - 申请并安装 Let’s Encrypt 证书（`certbot --nginx -d test.your-domain.com`）。

3) 验证
- `https://test.your-domain.com/healthz` 应返回 `{"status":"ok"}`
- `https://test.your-domain.com/api/products` 应返回 JSON
- 图片链接前缀为 `https://test.your-domain.com/static/images/...`

4) 微信小程序白名单
- 在“服务器域名”中增加测试域名：
   - request 合法域名：`https://test.your-domain.com`
   - downloadFile 合法域名：`https://test.your-domain.com`
- 注意：仅用于测试/体验版时可添加；正式版请保持生产域名。

5) 前端切换（可选）
- 临时切换：手工改 `miniprogram/app.js` 中的 `apiBaseUrl` 指向测试域名并重新编译预览。
- 或实现可配置切换（例如通过本地存储或 URL 参数设置覆盖），以便无需改代码即可切换环境。