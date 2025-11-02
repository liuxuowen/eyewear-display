import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import requests

# 在导入任何依赖于环境变量的模块之前，先加载 .env
envfile = Path(__file__).with_name('.env')
load_dotenv(dotenv_path=envfile)

from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from models import db, Product, User, PageView
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config.from_object(Config)
logger = logging.getLogger(__name__)

# 统一日志格式
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)

# 更严格的 CORS：仅作用于 /api/*，并按配置限制来源
cors_origins = app.config.get('CORS_ORIGINS', '*')
cors_resources = {r"/api/*": {"origins": cors_origins}}
CORS(app, resources=cors_resources, supports_credentials=False)

db.init_app(app)

# 生产环境关键配置校验
if app.config.get('ENV') == 'production':
    # 信任来自反向代理的 X-Forwarded-* 头，确保 request.is_secure 等判断正确
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    if app.config.get('JWT_SECRET_KEY') in (None, '', 'your-secret-key'):
        raise RuntimeError('In production, JWT_SECRET_KEY must be set via environment variable and not use the default!')

# 可选：自动创建缺失的数据表（仅在设置环境变量 AUTO_CREATE_DB=1 时执行）
if os.getenv('AUTO_CREATE_DB', '0').lower() in ('1', 'true', 'yes'):
    with app.app_context():
        db.create_all()

@app.after_request
def set_security_headers(resp):
    # 基础安全响应头
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    # 仅 API 响应；CSP 对纯 API 影响有限，但可作为保守默认
    resp.headers.setdefault('Content-Security-Policy', "default-src 'none'; img-src 'self' data:; connect-src 'self'")
    # HSTS：仅在启用 HTTPS 或强制 HTTPS 时设置
    if request.is_secure or app.config.get('FORCE_HTTPS'):
        resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    return resp

def paginate_query(query, page, per_page):
    """通用分页函数"""
    return query.paginate(page=page, per_page=per_page, error_out=False)

def handle_error(e, message="An error occurred"):
    """通用错误处理函数"""
    logging.error(f"{message}: {e}")
    # 生产环境隐藏具体错误信息
    if app.config.get('ENV') == 'production':
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    return jsonify({'status': 'error', 'message': str(e)}), 500

def _build_public_image_url(path: str) -> str:
    """将数据库中的图片相对路径/文件名转换为可被前端直接访问的完整 URL。
    规则：
    - 若 path 已是 http(s) 开头，原样返回；
    - 若 IMAGE_URL_PREFIX 以 http(s) 开头，返回 prefix + path；
    - 否则使用当前请求的 host_url + 相对前缀 组合为绝对 URL。
    """
    if not path:
        return path
    lower = path.lower()
    if lower.startswith('http://') or lower.startswith('https://'):
        return path

    prefix = app.config.get('IMAGE_URL_PREFIX', '/static/images/') or '/static/images/'
    # 统一去除/添加，避免重复斜杠
    if prefix.lower().startswith('http://') or prefix.lower().startswith('https://'):
        return prefix.rstrip('/') + '/' + path.lstrip('/')
    # 相对前缀，基于当前请求构造绝对 URL
    base = request.host_url.rstrip('/')
    rel = '/' + prefix.strip('/') + '/' + path.lstrip('/')
    return base + rel

def _serialize_product_with_public_images(product: Product) -> dict:
    d = product.to_dict()
    imgs = d.get('images', []) or []
    d['images'] = [_build_public_image_url(p) for p in imgs]
    return d


def _client_ip() -> str:
    # 在 ProxyFix 之后，request.access_route 会包含真实链路
    try:
        if request.access_route:
            return request.access_route[0]
    except Exception:
        pass
    return request.remote_addr or ''

@app.errorhandler(404)
def handle_404(_):
    return jsonify({'status': 'error', 'message': 'Not found'}), 404

@app.route('/healthz', methods=['GET'])
def healthz():
    return jsonify({'status': 'ok'}), 200

@app.route('/api/products', methods=['GET'])
def get_products():
    """获取产品列表"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        try:
            logger.info("/api/products query start page=%s per_page=%s args=%s", page, per_page, dict(request.args))
        except Exception:
            pass

        # 搜索参数（精确匹配）
        search_field = (request.args.get('search_field') or '').strip()
        search_value = (request.args.get('search_value') or '').strip()
        allowed_fields = getattr(app.config, 'ALLOWED_SEARCH_FIELDS', None) or app.config.get('ALLOWED_SEARCH_FIELDS', ['frame_model'])
        # 多字段并行过滤：从查询参数中抓取所有白名单字段
        multi_filters = {}
        for f in allowed_fields:
            v = request.args.get(f, type=str)
            if v is not None and str(v).strip() != '':
                multi_filters[f] = str(v).strip()

        query = Product.query.filter_by(is_active='是')
        numeric_fields = {'lens_size', 'nose_bridge_width', 'temple_length', 'frame_total_length', 'frame_height'}

        if multi_filters:
            # 同时应用多字段过滤（AND）
            for f, v in multi_filters.items():
                col = getattr(Product, f, None)
                if col is None:
                    continue
                if f in numeric_fields:
                    try:
                        value_num = float(v)
                        eps = 1e-4
                        query = query.filter(col.between(value_num - eps, value_num + eps))
                        logger.debug("apply numeric filter %s ~= %s (eps=%s)", f, value_num, eps)
                    except ValueError:
                        # 非法数值，令整体结果为空
                        query = query.filter(False)
                        logger.debug("invalid numeric filter for %s: %s", f, v)
                else:
                    query = query.filter(col == v)
                    logger.debug("apply text filter %s = %s", f, v)
            try:
                logger.info("/api/products using multi filters: %s", multi_filters)
            except Exception:
                pass
        elif search_value:
            # 兼容旧的单字段搜索参数
            if not search_field or search_field not in allowed_fields:
                search_field = app.config.get('DEFAULT_SEARCH_FIELD', 'frame_model')
            col = getattr(Product, search_field, None)
            if col is not None:
                if search_field in numeric_fields:
                    try:
                        value_num = float(search_value)
                        eps = 1e-4
                        query = query.filter(col.between(value_num - eps, value_num + eps))
                        logger.debug("apply numeric single filter %s ~= %s (eps=%s)", search_field, value_num, eps)
                    except ValueError:
                        query = query.filter(False)
                        logger.debug("invalid numeric single filter %s: %s", search_field, search_value)
                else:
                    query = query.filter(col == search_value)
                    logger.debug("apply text single filter %s = %s", search_field, search_value)
            try:
                logger.info("/api/products using single filter: %s=%s", search_field, search_value)
            except Exception:
                pass

        products = paginate_query(query, page, per_page)

        try:
            logger.info("/api/products query done total=%s pages=%s current_page=%s count=%s", products.total, products.pages, products.page, len(products.items))
        except Exception:
            pass

        return jsonify({
            'status': 'success',
            'data': {
                'items': [_serialize_product_with_public_images(product) for product in products.items],
                'total': products.total,
                'pages': products.pages,
                'current_page': products.page
            }
        })
    except Exception as e:
        return handle_error(e, "Error getting products")

@app.route('/api/products/<string:frame_model>', methods=['GET'])
def get_product(frame_model):
    """获取单个产品详情"""
    try:
        product = Product.query.filter_by(frame_model=frame_model, is_active='是').first()
        if not product:
            return jsonify({'status': 'error', 'message': '商品不存在'}), 404

        return jsonify({
            'status': 'success',
            'data': _serialize_product_with_public_images(product)
        })
    except Exception as e:
        return handle_error(e, f"Error getting product {frame_model}")


# === 用户与访问记录 API ===

@app.route('/api/users/upsert', methods=['POST'])
def upsert_user():
    """创建或更新用户（以微信 open_id 为主键）。
    Body JSON: { open_id: string, nickname?: string, avatar_url?: string }
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400

        nickname = (data.get('nickname') or '').strip() or None
        avatar_url = (data.get('avatar_url') or '').strip() or None

        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id, nickname=nickname, avatar_url=avatar_url)
            db.session.add(user)
        else:
            # 仅当传入新值时更新
            if nickname is not None:
                user.nickname = nickname
            if avatar_url is not None:
                user.avatar_url = avatar_url
        db.session.commit()
        return jsonify({'status': 'success', 'data': user.to_dict()})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error upserting user')


@app.route('/api/analytics/pageview', methods=['POST'])
def track_pageview():
    """记录用户访问页面。
    Body JSON: { open_id: string, page: string }
    附加自动采集：referer、user_agent、ip
    若用户不存在，将以 open_id 自动创建一个占位用户。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        page = (data.get('page') or '').strip()
        if not open_id or not page:
            return jsonify({'status': 'error', 'message': 'open_id and page are required'}), 400

        # 确保用户存在（占位创建）
        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id)
            db.session.add(user)

        pv = PageView(
            open_id=open_id,
            page=page,
            referer=request.headers.get('Referer'),
            user_agent=request.headers.get('User-Agent'),
            ip=_client_ip(),
        )
        db.session.add(pv)
        db.session.commit()
        return jsonify({'status': 'success', 'data': pv.to_dict()})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error tracking pageview')


# === 微信 code2session ===
@app.route('/api/wechat/code2session', methods=['POST'])
def wechat_code2session():
    """通过 wx.login code 获取 openid 和 session_key。
    Body JSON: { code: string }
    需要在环境变量中配置 WECHAT_APPID 和 WECHAT_SECRET。
    """
    try:
        data = request.get_json(silent=True) or {}
        code = (data.get('code') or '').strip()
        if not code:
            return jsonify({'status': 'error', 'message': 'code is required'}), 400

        appid = os.getenv('WECHAT_APPID')
        secret = os.getenv('WECHAT_SECRET')
        if not appid or not secret:
            return jsonify({'status': 'error', 'message': 'WECHAT_APPID/WECHAT_SECRET not configured'}), 500

        params = {
            'appid': appid,
            'secret': secret,
            'js_code': code,
            'grant_type': 'authorization_code'
        }
        resp = requests.get('https://api.weixin.qq.com/sns/jscode2session', params=params, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        # 正常返回包含 openid 和 session_key；错误包含 errcode/errmsg
        if 'errcode' in payload and payload['errcode'] != 0:
            return jsonify({'status': 'error', 'message': payload.get('errmsg', 'code2session error'), 'errcode': payload.get('errcode')}), 400

        data_out = {
            'openid': payload.get('openid'),
            'session_key': payload.get('session_key'),
            'unionid': payload.get('unionid')
        }
        return jsonify({'status': 'success', 'data': data_out})
    except requests.RequestException as re:
        return handle_error(re, 'WeChat code2session request failed')
    except Exception as e:
        return handle_error(e, 'Error in code2session')

if __name__ == '__main__':
    # 仅用于开发。生产请使用 WSGI 服务器（如 gunicorn/uwsgi/waitress）并在反向代理后运行
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = app.config.get('DEBUG', False)
    app.run(debug=debug, host=host, port=port)