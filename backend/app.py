import os
import re
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
from models import db, Product, User, PageView, Favorite, Salesperson
from sqlalchemy import inspect, text, or_, select
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

# 轻量自检/自愈：确保 users 表存在 referrer_open_id / my_sales_open_id 字段（无迁移系统时的简易保障）
try:
    with app.app_context():
        insp = inspect(db.engine)
        if 'users' in insp.get_table_names():
            cols = [c['name'] for c in insp.get_columns('users')]
            if 'referrer_open_id' not in cols:
                try:
                    db.session.execute(text('ALTER TABLE users ADD COLUMN referrer_open_id VARCHAR(64)'))
                    db.session.commit()
                    logger.info('Added column users.referrer_open_id via ALTER TABLE')
                except Exception as e:
                    db.session.rollback()
                    logger.warning('Ensure referrer_open_id failed (may already exist or unsupported): %s', e)
            if 'my_sales_open_id' not in cols:
                try:
                    db.session.execute(text('ALTER TABLE users ADD COLUMN my_sales_open_id VARCHAR(64)'))
                    db.session.commit()
                    logger.info('Added column users.my_sales_open_id via ALTER TABLE')
                except Exception as e:
                    db.session.rollback()
                    logger.warning('Ensure my_sales_open_id failed (may already exist or unsupported): %s', e)
except Exception as e:
    logger.warning('Startup column check skipped: %s', e)

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
    # 清洗后端常见占位字符串（例如 'None', 'null' 等）为实际空值，避免前端展示奇怪文本
    def _clean_text(x):
        if isinstance(x, str):
            t = x.strip()
            if t.lower() in ('none', 'null', 'undefined', 'nan'):
                return ''
            return t
        return x
    if 'brand' in d:
        d['brand'] = _clean_text(d.get('brand'))
    if 'notes' in d:
        d['notes'] = _clean_text(d.get('notes'))
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
        # try:
        #     logger.info("/api/products query start page=%s per_page=%s args=%s", page, per_page, dict(request.args))
        # except Exception:
        #     pass

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
        numeric_fields = {'lens_size', 'nose_bridge_width', 'temple_length', 'frame_total_length', 'frame_height', 'weight', 'price'}

        def _material_match_any(col, tags):
            """构造“材质标签”匹配条件：
            - tags: 可迭代的标签（如 ['TR','B钛']）
            - 数据库存储格式示例："TR+钛"、"TR+B钛"；按'+'分隔为精确标签
            - 精确匹配策略（避免子串误命中）：
              col = tag OR col LIKE 'tag+%' OR col LIKE '%+tag' OR col LIKE '%+tag+%'
            """
            conds = []
            for raw in tags:
                tag = (raw or '').strip()
                if not tag:
                    continue
                like_mid = f"%+{tag}+%"
                like_head = f"{tag}+%"
                like_tail = f"%+{tag}"
                conds.append(or_(col == tag, col.like(like_head), col.like(like_tail), col.like(like_mid)))
            if not conds:
                return None
            # 任一命中即可
            out = conds[0]
            for c in conds[1:]:
                out = or_(out, c)
            return out

        def _parse_range_or_number(s: str):
            """解析数值或范围字符串，支持：
            - 单值: "42" -> (42.0, 42.0)
            - 范围: "40-45" / "40 - 45" -> (40.0, 45.0)
            返回: (lo, hi) 或抛出 ValueError
            """
            if s is None:
                raise ValueError('empty')
            text = str(s).strip()
            # 兼容中文破折号、全角连字符
            text = text.replace('－', '-').replace('—', '-').replace('–', '-')
            if '-' in text:
                parts = [p.strip() for p in text.split('-', 1)]
                if len(parts) != 2 or parts[0] == '' or parts[1] == '':
                    raise ValueError('invalid range')
                lo = float(parts[0])
                hi = float(parts[1])
                if lo > hi:
                    lo, hi = hi, lo
                return (lo, hi)
            # 单值
            v = float(text)
            return (v, v)

        if multi_filters:
            # 同时应用多字段过滤（AND）
            for f, v in multi_filters.items():
                if f == 'other_info':
                    # 其他信息：恢复为品牌或备注任一模糊匹配
                    like = f"%{v}%"
                    query = query.filter(or_(Product.brand.like(like), Product.notes.like(like)))
                    logger.debug("apply fuzzy filter other_info (brand or notes) like %s", like)
                    continue
                if f == 'brand_info':
                    # 品牌信息：仅在品牌字段模糊匹配
                    like = f"%{v}%"
                    query = query.filter(Product.brand.like(like))
                    logger.debug("apply fuzzy filter brand_info (brand only) like %s", like)
                    continue
                if f == 'frame_material':
                    # 解析为多选标签，分隔符支持逗号/中文逗号/竖线
                    parts = [p.strip() for p in re.split(r'[，,|]+', v) if p and p.strip()]
                    cond = _material_match_any(Product.frame_material, parts)
                    if cond is not None:
                        query = query.filter(cond)
                        logger.debug("apply material any-of tags: %s", parts)
                    continue
                col = getattr(Product, f, None)
                if col is None:
                    continue
                if f in numeric_fields:
                    try:
                        lo, hi = _parse_range_or_number(v)
                        eps = 1e-4
                        query = query.filter(col.between(lo - eps, hi + eps))
                        if lo == hi:
                            logger.debug("apply numeric filter %s ~= %s (eps=%s)", f, lo, eps)
                        else:
                            logger.debug("apply numeric filter %s in [%s, %s] (eps=%s)", f, lo, hi, eps)
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
            if search_field == 'other_info':
                like = f"%{search_value}%"
                query = query.filter(or_(Product.brand.like(like), Product.notes.like(like)))
                logger.debug("apply single fuzzy other_info (brand or notes) like %s", like)
            elif search_field == 'brand_info':
                like = f"%{search_value}%"
                query = query.filter(Product.brand.like(like))
                logger.debug("apply single fuzzy brand_info (brand only) like %s", like)
            elif search_field == 'frame_material':
                parts = [p.strip() for p in re.split(r'[，,|]+', search_value) if p and p.strip()]
                cond = _material_match_any(Product.frame_material, parts)
                if cond is not None:
                    query = query.filter(cond)
                    logger.debug("apply single material any-of tags: %s", parts)
            elif col is not None:
                if search_field in numeric_fields:
                    try:
                        lo, hi = _parse_range_or_number(search_value)
                        eps = 1e-4
                        query = query.filter(col.between(lo - eps, hi + eps))
                        if lo == hi:
                            logger.debug("apply numeric single filter %s ~= %s (eps=%s)", search_field, lo, eps)
                        else:
                            logger.debug("apply numeric single filter %s in [%s, %s] (eps=%s)", search_field, lo, hi, eps)
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

        # try:
        #     logger.info("/api/products query done total=%s pages=%s current_page=%s count=%s", products.total, products.pages, products.page, len(products.items))
        # except Exception:
        #     pass

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


# === 收藏（Watchlist / Favorites） ===

@app.route('/api/favorites', methods=['GET'])
def list_favorites():
    """列出某用户收藏的商品（按加入时间倒序）。
    Query: open_id (required), page, per_page
    返回商品列表（仅展示 is_active=是 的商品）。
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        # 子查询获取用户收藏的 frame_model 列表
        # 使用显式 select() 构造，避免 SQLAlchemy 发出 Subquery -> select 的警告
        subq = select(Favorite.frame_model).where(Favorite.open_id == open_id)
        # 只返回仍有效的商品
        query = Product.query.filter(Product.frame_model.in_(subq)).filter_by(is_active='是')

        products = paginate_query(query, page, per_page)
        return jsonify({
            'status': 'success',
            'data': {
                'items': [_serialize_product_with_public_images(p) for p in products.items],
                'total': products.total,
                'pages': products.pages,
                'current_page': products.page
            }
        })
    except Exception as e:
        return handle_error(e, 'Error listing favorites')


@app.route('/api/favorites/ids', methods=['GET'])
def list_favorite_ids():
    """获取用户收藏的型号列表。
    Query: open_id (required)
    Return: { items: [frame_model, ...] }
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400
        ids = [row.frame_model for row in Favorite.query.with_entities(Favorite.frame_model).filter_by(open_id=open_id).all()]
        return jsonify({'status': 'success', 'data': {'items': ids}})
    except Exception as e:
        return handle_error(e, 'Error listing favorite ids')


@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """添加收藏（幂等）。Body: { open_id, frame_model }
    如用户不存在，则占位创建用户。重复收藏不会报错。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        frame_model = (data.get('frame_model') or '').strip()
        if not open_id or not frame_model:
            return jsonify({'status': 'error', 'message': 'open_id and frame_model are required'}), 400

        # 确保用户存在
        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id)
            db.session.add(user)

        # 检查商品存在
        product = Product.query.filter_by(frame_model=frame_model, is_active='是').first()
        if not product:
            return jsonify({'status': 'error', 'message': '商品不存在或未上架'}), 404

        # 幂等插入
        exists = Favorite.query.filter_by(open_id=open_id, frame_model=frame_model).first()
        if not exists:
            fav = Favorite(open_id=open_id, frame_model=frame_model)
            db.session.add(fav)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error adding favorite')


@app.route('/api/favorites', methods=['DELETE'])
def remove_favorite():
    """取消收藏。Body: { open_id, frame_model }"""
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        frame_model = (data.get('frame_model') or '').strip()
        if not open_id or not frame_model:
            return jsonify({'status': 'error', 'message': 'open_id and frame_model are required'}), 400
        Favorite.query.filter_by(open_id=open_id, frame_model=frame_model).delete()
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error removing favorite')


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
        referrer_open_id = (data.get('referrer_open_id') or '').strip() or None

        user = User.query.get(open_id)
        if not user:
            # 创建新用户时可带上 referrer_open_id
            if referrer_open_id == open_id:
                referrer_open_id = None  # 自己不能作为自己的介绍人
            user = User(open_id=open_id, nickname=nickname, avatar_url=avatar_url, referrer_open_id=referrer_open_id)
            db.session.add(user)
        else:
            # 仅当传入新值时更新
            if nickname is not None:
                user.nickname = nickname
            if avatar_url is not None:
                user.avatar_url = avatar_url
            # 设置介绍人：只允许设置一次；若已存在且不同则拒绝覆盖；同值则幂等
            if referrer_open_id is not None:
                if referrer_open_id == open_id:
                    return jsonify({'status': 'error', 'message': 'referrer cannot be self'}), 400
                current = (user.referrer_open_id or '').strip()
                incoming = referrer_open_id
                if not current:
                    user.referrer_open_id = incoming
                elif current == incoming:
                    pass  # 幂等：相同值不做更新
                else:
                    return jsonify({'status': 'error', 'message': 'referrer already set and cannot be changed'}), 400
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


# === 用户推荐关系（只允许设置一次） ===
@app.route('/api/users/referrer', methods=['POST'])
def set_user_referrer():
    """设置用户的介绍人（仅允许设置一次）。
    Body JSON: { open_id: string, referrer_open_id: string }
    规则：
    - open_id 与 referrer_open_id 不能相同；
    - 若用户不存在，将占位创建；
    - 若 referrer_open_id 已存在且与现有不同，则返回 400，拒绝覆盖；
    - 若 referrer_open_id 已存在且与传入相同，则幂等成功；
    - 若当前为空，则设置为传入值。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        referrer_open_id = (data.get('referrer_open_id') or '').strip()
        if not open_id or not referrer_open_id:
            return jsonify({'status': 'error', 'message': 'open_id and referrer_open_id are required'}), 400
        if open_id == referrer_open_id:
            return jsonify({'status': 'error', 'message': 'referrer cannot be self'}), 400

        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id)
            db.session.add(user)

        current = (user.referrer_open_id or '').strip()
        if not current:
            user.referrer_open_id = referrer_open_id
            db.session.commit()
            return jsonify({'status': 'success', 'data': user.to_dict()})
        if current == referrer_open_id:
            return jsonify({'status': 'success', 'data': user.to_dict()})  # 幂等
        return jsonify({'status': 'error', 'message': 'referrer already set and cannot be changed'}), 400
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error setting referrer')


@app.route('/api/users/mysales', methods=['POST'])
def set_user_my_sales():
    """设置用户的“我的销售”（仅允许设置一次）。
    Body JSON: { open_id: string, my_sales_open_id: string }
    规则：
    - open_id 与 my_sales_open_id 不能相同；
    - 若用户不存在，将占位创建；
    - 若 my_sales_open_id 已存在且与现有不同，则返回 400；
    - 若相同则幂等成功；
    - 若当前为空则设置。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        my_sales_open_id = (data.get('my_sales_open_id') or '').strip()
        if not open_id or not my_sales_open_id:
            return jsonify({'status': 'error', 'message': 'open_id and my_sales_open_id are required'}), 400
        if open_id == my_sales_open_id:
            return jsonify({'status': 'error', 'message': 'my_sales cannot be self'}), 400

        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id)
            db.session.add(user)

        current = (user.my_sales_open_id or '').strip()
        if not current:
            user.my_sales_open_id = my_sales_open_id
            db.session.commit()
            return jsonify({'status': 'success', 'data': user.to_dict()})
        if current == my_sales_open_id:
            return jsonify({'status': 'success', 'data': user.to_dict()})
        return jsonify({'status': 'error', 'message': 'my_sales already set and cannot be changed'}), 400
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error setting my sales')


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


@app.route('/api/users/role', methods=['GET'])
def get_user_role():
    """根据 open_id 返回角色信息。来源：数据库 sales 表。
    Query: open_id
    Return: { role: 'sales' | 'user', has_my_sales: bool, my_sales_open_id: str|null, my_sales_name: str|null }
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400
        is_sales = Salesperson.query.filter_by(open_id=open_id).first() is not None
        role = 'sales' if is_sales else 'user'
        # 返回是否已分配“我的销售”，便于前端按角色与分配态控制 UI
        user = User.query.get(open_id)
        my_sales_open_id = None
        my_sales_name = None
        if user and (user.my_sales_open_id or '').strip():
            my_sales_open_id = (user.my_sales_open_id or '').strip()
            try:
                sp = Salesperson.query.filter_by(open_id=my_sales_open_id).first()
                if sp and (sp.name or '').strip():
                    my_sales_name = (sp.name or '').strip()
            except Exception:
                my_sales_name = None
        has_my_sales = bool(my_sales_open_id)
        return jsonify({'status': 'success', 'data': {
            'role': role,
            'has_my_sales': has_my_sales,
            'my_sales_open_id': my_sales_open_id,
            'my_sales_name': my_sales_name
        }})
    except Exception as e:
        return handle_error(e, 'Error getting user role')

@app.route('/api/kf/context', methods=['GET'])
def get_kf_context():
    """提供客服会话所需的上下文：
    输入：open_id（当前访客 B）
    输出：
      - referrer_nickname：用户 B 的推荐人 A 的昵称（数据库中 User.nickname；无则返回“自然”）
      - sales_name：用户 B 的推荐人 A 的销售的姓名（通过 A.my_sales_open_id 关联 sales 表；无则返回“自然”）
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400

        referrer_name = '自然'
        sales_name = '自然'

        user = User.query.get(open_id)
        if user and user.referrer_open_id:
            ref_user = User.query.get(user.referrer_open_id)
            if ref_user:
                nn = (ref_user.nickname or '').strip()
                if nn:
                    referrer_name = nn
                # 取推荐人 A 的销售姓名
                msid = (ref_user.my_sales_open_id or '').strip()
                if msid:
                    sp = Salesperson.query.filter_by(open_id=msid).first()
                    if sp and (sp.name or '').strip():
                        sales_name = (sp.name or '').strip()

        return jsonify({'status': 'success', 'data': {
            'referrer_nickname': referrer_name,
            'sales_name': sales_name
        }})
    except Exception as e:
        return handle_error(e, 'Error getting kf context')

@app.route('/api/sales', methods=['GET'])
def list_sales():
    """列出已登记的销售（用于校验/查看）。
    Return: { items: [{id, open_id, name}, ...] }
    """
    try:
        items = [s.to_dict() for s in Salesperson.query.order_by(Salesperson.id.asc()).all()]
        return jsonify({'status': 'success', 'data': {'items': items}})
    except Exception as e:
        return handle_error(e, 'Error listing sales')

@app.route('/api/users/referrals', methods=['GET'])
def list_user_referrals():
    """列出某用户的转介绍人员列表（被其推荐注册/访问的用户）。
    Query: open_id (required)
    Return: { items: [{ open_id, nickname }], total: n }
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400

        q = User.query.with_entities(User.open_id, User.nickname).filter(User.referrer_open_id == open_id)
        # 优先按创建时间倒序，如无则按 open_id
        try:
            q = q.order_by(User.created_at.desc())
        except Exception:
            q = q.order_by(User.open_id.asc())

        rows = q.all()
        items = [{'open_id': r.open_id, 'nickname': (r.nickname or '')} for r in rows]
        return jsonify({'status': 'success', 'data': {'items': items, 'total': len(items)}})
    except Exception as e:
        return handle_error(e, 'Error listing user referrals')


@app.route('/api/favorites/batch', methods=['POST'])
def add_favorites_batch():
    """批量添加收藏（幂等）。Body: { open_id: str, frame_models: [str, ...] }
    忽略无效或未上架的商品；返回成功加入的数量。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        items = data.get('frame_models') or []
        if not open_id or not isinstance(items, list):
            return jsonify({'status': 'error', 'message': 'open_id and frame_models(list) are required'}), 400

        # 确保用户存在
        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id)
            db.session.add(user)

        # 去重并裁剪数量（上限 50，避免过载；前端会控制 10）
        uniq = []
        seen = set()
        for m in items:
            if not m or not isinstance(m, str):
                continue
            mm = m.strip()
            if not mm or mm in seen:
                continue
            seen.add(mm)
            uniq.append(mm)
            if len(uniq) >= 50:
                break

        if not uniq:
            return jsonify({'status': 'success', 'data': {'added': 0}})

        # 查询有效商品
        valid = Product.query.with_entities(Product.frame_model).filter(Product.is_active == '是', Product.frame_model.in_(uniq)).all()
        valid_set = {row.frame_model for row in valid}

        # 现有收藏
        existing = Favorite.query.with_entities(Favorite.frame_model).filter(Favorite.open_id == open_id, Favorite.frame_model.in_(list(valid_set))).all()
        exist_set = {row.frame_model for row in existing}

        # 批量添加
        added = 0
        for fm in valid_set:
            if fm in exist_set:
                continue
            db.session.add(Favorite(open_id=open_id, frame_model=fm))
            added += 1
        db.session.commit()
        return jsonify({'status': 'success', 'data': {'added': added}})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error adding favorites batch')

if __name__ == '__main__':
    # 仅用于开发。生产请使用 WSGI 服务器（如 gunicorn/uwsgi/waitress）并在反向代理后运行
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = app.config.get('DEBUG', False)
    app.run(debug=debug, host=host, port=port)