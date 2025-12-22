# test
import os
import re
import json
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
import requests

# 在导入任何依赖于环境变量的模块之前，先加载 .env
envfile = Path(__file__).with_name('.env')
load_dotenv(dotenv_path=envfile)

from flask import Flask, jsonify, request, g, has_request_context, render_template, make_response, url_for
from flask_cors import CORS
from config import Config
from models import db, Product, User, PageView, Favorite, Salesperson, SalesShare
from sqlalchemy import inspect, text, or_, select, func
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.from_object(Config)
logger = logging.getLogger(__name__)

# === 时间格式化（北京时间显示）===
# 后台展示需要将数据库中以 UTC 记录的时间戳转换为北京时间 (UTC+8)。
from datetime import timedelta, timezone, datetime
CN_UTC_OFFSET = timedelta(hours=8)

def to_beijing(dt):
    """将 datetime 格式化为北京时间字符串。
    现约定：数据库已直接存储北京时间（naive）。
    - 若为 naive，直接格式化；
    - 若为 tz-aware，则转换到 UTC+8 再格式化。
    格式：YYYY-MM-DD HH:MM:SS
    """
    if not dt:
        return ''
    try:
        if dt.tzinfo is None:
            local = dt
        else:
            local = dt.astimezone(timezone(CN_UTC_OFFSET)).replace(tzinfo=None)
        return local.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(dt)

app.jinja_env.filters['cn_time'] = to_beijing

def now_cn():
    """返回北京时间(UTC+8)的当前时间（naive datetime）。"""
    try:
        return (datetime.utcnow() + CN_UTC_OFFSET).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()

# 统一日志格式（追加 open_id 上下文）
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s oid=%(open_id)s %(message)s'
)


class OpenIdInjectFilter(logging.Filter):
    """将当前请求中的 open_id 注入日志记录的 record.open_id 字段。
    若无请求上下文或无法解析，则记为 '-'.
    """
    PARAM_CANDIDATES = (
        'open_id', 'customer_open_id', 'salesperson_open_id',
        'my_sales_open_id', 'referrer_open_id', 'openid', 'sid'
    )

    @classmethod
    def _extract_from_request(cls):
        try:
            # 优先使用 before_request 捕获到的值
            oid = getattr(g, '_log_open_id', None) if has_request_context() else None
        except Exception:
            oid = None
        try:
            if has_request_context():
                if not oid:
                    # args/form
                    for k in cls.PARAM_CANDIDATES:
                        v = request.values.get(k)
                        if v:
                            oid = v
                            break
                if not oid and (request.is_json or request.mimetype == 'application/json'):
                    data = request.get_json(silent=True) or {}
                    for k in cls.PARAM_CANDIDATES:
                        v = data.get(k)
                        if v:
                            oid = v
                            break
        except Exception:
            pass
        return oid

    def filter(self, record: logging.LogRecord) -> bool:
        oid = '-'
        try:
            if has_request_context():
                x = self._extract_from_request()
                if x:
                    oid = str(x)
        except Exception:
            pass
        # 为避免 KeyError，确保总是设置该字段
        record.open_id = oid
        return True


# 将过滤器挂到所有现有 handler 上
_oid_filter = OpenIdInjectFilter()
_root_logger = logging.getLogger()
for _h in _root_logger.handlers:
    _h.addFilter(_oid_filter)
# 也挂到当前模块 logger（以防外部 handler 未继承 root 的过滤器）
logger.addFilter(_oid_filter)

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
        # 确保 favorites 表新增批次列存在
        if 'favorites' in insp.get_table_names():
            fav_cols = [c['name'] for c in insp.get_columns('favorites')]
            def _ensure_fav_col(name, ddl):
                if name not in fav_cols:
                    try:
                        db.session.execute(text(f'ALTER TABLE favorites ADD COLUMN {ddl}'))
                        db.session.commit()
                        logger.info('Added column favorites.%s', name)
                    except Exception as ie:
                        db.session.rollback()
                        logger.warning('Ensure favorites.%s failed (may already exist or unsupported): %s', name, ie)
            _ensure_fav_col('batch_id', 'batch_id INTEGER NULL')
            _ensure_fav_col('batch_time', 'batch_time DATETIME NULL')
        # 轻量自检：sales_shares 表，若不存在则创建（无需完整迁移系统）
        if 'sales_shares' not in insp.get_table_names():
            try:
                SalesShare.__table__.create(bind=db.engine)
                logger.info('Created table sales_shares')
            except Exception as e:
                logger.warning('Create sales_shares failed (may already exist or unsupported): %s', e)
        else:
            # 确保新增列存在（简单列检查再尝试 ALTER）
            try:
                share_cols = [c['name'] for c in insp.get_columns('sales_shares')]
                def ensure_column(col_name, ddl):
                    if col_name not in share_cols:
                        try:
                            db.session.execute(text(f'ALTER TABLE sales_shares ADD COLUMN {ddl}'))
                            db.session.commit()
                            logger.info('Added column sales_shares.%s', col_name)
                        except Exception as ie:
                            db.session.rollback()
                            logger.warning('Ensure column sales_shares.%s failed: %s', col_name, ie)
                ensure_column('is_sent', 'is_sent BOOLEAN NOT NULL DEFAULT 0')
                ensure_column('sent_count', 'sent_count INTEGER NOT NULL DEFAULT 0')
                ensure_column('last_sent_time', 'last_sent_time DATETIME NULL')
                ensure_column('note', 'note VARCHAR(64) NULL')
                ensure_column('dedup_key', 'dedup_key VARCHAR(128) NULL')
                # 尝试为 dedup_key 创建唯一索引（若已存在则忽略）
                try:
                    idx_list = insp.get_indexes('sales_shares')
                    idx_names = {i.get('name') for i in idx_list}
                    has_dedup_idx = any('dedup' in (n or '').lower() for n in idx_names)
                    if not has_dedup_idx:
                        # MySQL/SQLite 兼容写法：不使用 IF NOT EXISTS，失败则忽略
                        db.session.execute(text('CREATE UNIQUE INDEX idx_sales_shares_dedup ON sales_shares(dedup_key)'))
                        db.session.commit()
                        logger.info('Created unique index idx_sales_shares_dedup on sales_shares(dedup_key)')
                except Exception as ie:
                    db.session.rollback()
                    logger.warning('Ensure unique index on sales_shares.dedup_key failed or exists: %s', ie)
            except Exception as e:
                logger.warning('sales_shares column ensure skipped: %s', e)
except Exception as e:
    logger.warning('Startup column check skipped: %s', e)


@app.before_request
def _capture_openid_for_logging():
    """在请求开始时尝试抓取 open_id（或等价参数）存入 g，便于日志统一输出。"""
    try:
        candidates = (
            'open_id', 'customer_open_id', 'salesperson_open_id',
            'my_sales_open_id', 'referrer_open_id', 'openid', 'sid'
        )
        oid = None
        # args/form 优先
        for k in candidates:
            v = request.values.get(k)
            if v:
                oid = v
                break
        if not oid and (request.is_json or request.mimetype == 'application/json'):
            data = request.get_json(silent=True) or {}
            for k in candidates:
                v = data.get(k)
                if v:
                    oid = v
                    break
        g._log_open_id = oid
    except Exception:
        try:
            g._log_open_id = None
        except Exception:
            pass

@app.after_request
def set_security_headers(resp):
    # 基础安全响应头
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    # 仅 API 响应；CSP 对纯 API 影响有限，但可作为保守默认
    resp.headers.setdefault('Content-Security-Policy', "default-src 'none'; img-src 'self' data:; connect-src 'self'")
    # API 禁止缓存，确保客户端总是拿到最新数据
    try:
        p = (request.path or '')
        if p.startswith('/api/'):
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
    except Exception:
        pass
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

def _allowed_image(mimetype: str) -> bool:
    return mimetype in ('image/jpeg', 'image/png', 'image/jpg')

def _avatar_public_url(filename: str) -> str:
    base = request.host_url.rstrip('/')
    return f"{base}/static/avatars/{filename}"

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

@app.route('/api/system/config', methods=['GET'])
def get_system_config():
    """获取系统全局配置（如生产模式开关）"""
    return jsonify({
        'status': 'success',
        'data': {
            'is_production_mode': app.config.get('IS_PRODUCTION_MODE', False),
            'enable_customer_referrals': app.config.get('ENABLE_CUSTOMER_REFERRALS', True)
        }
    })

@app.route('/api/products', methods=['GET'])
def get_products():
    """获取产品列表"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

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
                if f == 'frame_model':
                    # 镜架型号：忽略大小写的子串匹配（如搜索 123 可匹配到 s123）
                    needle = (v or '').strip().lower()
                    like = f"%{needle}%"
                    query = query.filter(func.lower(Product.frame_model).like(like))
                    logger.debug("apply fuzzy filter frame_model (case-insensitive contains) like %s", like)
                    continue
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
            if search_field == 'frame_model':
                # 镜架型号：忽略大小写的子串匹配（如搜索 123 可匹配到 s123）
                needle = (search_value or '').strip().lower()
                like = f"%{needle}%"
                query = query.filter(func.lower(Product.frame_model).like(like))
                logger.debug("apply single fuzzy frame_model (case-insensitive contains) like %s", like)
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


# === 文件上传：头像 ===
@app.route('/api/upload/avatar', methods=['POST'])
def upload_avatar():
    """上传用户头像文件，返回可长期访问的公网 URL。
    Form: open_id, file (multipart)
    Return: { status, url }
    """
    try:
        logger.info('avatar upload debug form_keys=%s files_keys=%s', list(request.form.keys()), list(request.files.keys()))

        open_id = (request.form.get('open_id') or '').strip()
        f = request.files.get('file')
        remote_url = (request.form.get('remote_url') or request.form.get('avatar_url') or '').strip()
        logger.info('avatar upload debug form_keys=%s files_keys=%s open_id=%r remote_url=%r', list(request.form.keys()), list(request.files.keys()), open_id, remote_url)
        if not open_id:
            logger.warning('avatar upload missing open_id')
            return jsonify({'status': 'error', 'message': 'open_id missing'}), 400
        if not f and not remote_url:
            logger.warning('avatar upload missing file and remote_url (open_id=%r)', open_id)
            return jsonify({'status': 'error', 'message': 'file or remote_url required'}), 400

        # 若本地文件存在，走本地上传；否则尝试远程下载
        content_bytes = None
        content_type = None
        if f is not None:
            # 基本校验
            if not _allowed_image(f.mimetype):
                logger.warning('avatar upload unsupported mimetype %r (open_id=%r)', f.mimetype, open_id)
                return jsonify({'status': 'error', 'message': 'unsupported file type'}), 400
            # 限制大小 2MB
            try:
                f.stream.seek(0, 2)
                size = f.stream.tell()
                f.stream.seek(0)
            except Exception:
                size = None
            if size is not None and size > 2 * 1024 * 1024:
                logger.warning('avatar upload too large size=%s bytes (open_id=%r, mimetype=%r)', size, open_id, f.mimetype)
                return jsonify({'status': 'error', 'message': 'file too large'}), 400
            logger.info('avatar upload received open_id=%r mimetype=%r size=%s', open_id, f.mimetype, size)
            content_type = f.mimetype
        else:
            # 远程下载：仅允许微信头像域名，避免滥用
            from urllib.parse import urlparse
            try:
                pr = urlparse(remote_url)
                host = (pr.hostname or '').lower()
                allowed_hosts = {'thirdwx.qlogo.cn', 'wx.qlogo.cn'}
                if host not in allowed_hosts:
                    logger.warning('avatar remote_url host not allowed: %r (open_id=%r)', host, open_id)
                    return jsonify({'status': 'error', 'message': 'remote host not allowed'}), 400
                r = requests.get(remote_url, timeout=5)
                r.raise_for_status()
                content_type = r.headers.get('Content-Type', '')
                if not _allowed_image(content_type):
                    logger.warning('avatar remote content-type unsupported: %r (open_id=%r)', content_type, open_id)
                    return jsonify({'status': 'error', 'message': 'unsupported file type'}), 400
                content_bytes = r.content
                size = len(content_bytes)
                if size > 2 * 1024 * 1024:
                    logger.warning('avatar remote too large size=%s (open_id=%r)', size, open_id)
                    return jsonify({'status': 'error', 'message': 'file too large'}), 400
                logger.info('avatar remote fetched ok size=%s type=%r url=%r (open_id=%r)', size, content_type, remote_url, open_id)
            except Exception as de:
                logger.error('avatar remote fetch error url=%r open_id=%r err=%s', remote_url, open_id, de)
                return jsonify({'status': 'error', 'message': 'remote fetch failed'}), 400

        # 生成安全文件名
        ext = '.jpg'
        try:
            if (content_type or '').endswith('png'):
                ext = '.png'
        except Exception:
            pass
        safe = secure_filename(open_id) or 'user'
        # 使用 open_id 前缀 + 时间戳，避免频繁覆盖；如需覆盖可改为固定名
        filename = f"{safe}_{int(time.time())}{ext}"
        save_dir = Path(app.root_path) / 'static' / 'avatars'
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename
        if content_bytes is not None:
            with open(save_path, 'wb') as fp:
                fp.write(content_bytes)
        else:
            f.save(save_path)

        url = _avatar_public_url(filename)
        logger.info('avatar upload success open_id=%r filename=%r url=%r', open_id, filename, url)
        return jsonify({'status': 'success', 'url': url})
    except Exception as e:
        logger.error('avatar upload error open_id=%r err=%s', (request.form.get('open_id') or '').strip(), e)
        return handle_error(e, 'Error uploading avatar')


# === 推荐（Watchlist / Favorites） ===

@app.route('/api/favorites', methods=['GET'])
def list_favorites():
    """列出某用户推荐的商品。
    支持按推荐批次分组返回：若传 group_by=batch 则返回分组结构。
    Query:
      - open_id (required)
      - page, per_page （仅在非分组模式下分页产品）
      - group_by=batch 可启用批次分组模式（忽略分页，返回全部分组）
    批次定义：同一批推荐操作（批量接口或单次添加）生成唯一 batch_id 与 batch_time。
    未分配 batch_id 的旧数据归为 legacy 分组。
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400

        group_by = (request.args.get('group_by') or '').strip().lower()
        if group_by == 'batch':
            # 分组模式：拉取该用户所有 favorites 及对应产品（仅 is_active=是）
            # 兼容 MySQL 无 NULLS LAST：按 (batch_time IS NULL) 升序，将非空在前，再按 batch_time DESC, created_at DESC
            favs = (Favorite.query
                    .filter_by(open_id=open_id)
                    .order_by(Favorite.batch_time.is_(None), Favorite.batch_time.desc(), Favorite.created_at.desc())
                    .all())
            # 收集所有型号到产品查询
            frame_models = [f.frame_model for f in favs]
            if not frame_models:
                return jsonify({'status': 'success', 'data': {'batches': []}})
            products = Product.query.filter(Product.frame_model.in_(frame_models), Product.is_active == '是').all()
            prod_map = {p.frame_model: _serialize_product_with_public_images(p) for p in products}
            batches = []
            # 分组：batch_id 为 None -> legacy 单独处理，按 batch_time 逆序，其次 created_at
            from collections import OrderedDict
            grouped = OrderedDict()
            for f in favs:
                bid = f.batch_id if f.batch_id is not None else '__legacy__'
                key = bid
                if key not in grouped:
                    grouped[key] = {
                        'batch_id': f.batch_id,
                        'batch_time': f.batch_time.isoformat() if f.batch_time else None,
                        'items': []
                    }
                prod = prod_map.get(f.frame_model)
                if prod:
                    grouped[key]['items'].append(prod)
            # legacy 放最后，其余按 batch_time desc
            legacy = grouped.pop('__legacy__', None)
            # 转换为列表
            for k, v in grouped.items():
                batches.append(v)
            # 过滤空批次（可能全部失效）
            batches = [b for b in batches if b['items']]
            if legacy and legacy['items']:
                legacy['batch_time'] = None
                batches.append(legacy)
            return jsonify({'status': 'success', 'data': {'batches': batches}})
        else:
            page = int(request.args.get('page', 1))
            per_page = int(request.args.get('per_page', 10))
            subq = select(Favorite.frame_model).where(Favorite.open_id == open_id)
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
    """获取用户推荐的型号列表。
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
    """添加推荐（幂等）。Body: { open_id, frame_model }
    如用户不存在，则占位创建用户。重复推荐不会报错。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        frame_model = (data.get('frame_model') or '').strip()
        if not open_id or not frame_model:
            return jsonify({'status': 'error', 'message': 'open_id and frame_model are required'}), 400

        # 仅允许销售添加推荐
        try:
            is_sales = Salesperson.query.filter_by(open_id=open_id).first() is not None
        except Exception:
            is_sales = False
        if not is_sales:
            return jsonify({'status': 'error', 'message': 'only salesperson can add recommendation'}), 403

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
        # 生成批次：若请求带 batch_id 则尝试复用；否则新建
        incoming_batch_id = data.get('batch_id')
        batch_id = None
        batch_time = None
        try:
            if incoming_batch_id is not None:
                batch_id = int(incoming_batch_id)
        except Exception:
            batch_id = None
        if batch_id is None:
            # 为该用户生成新的 batch_id：取当前时间戳秒
            batch_id = int(time.time())
        batch_time = datetime.datetime.utcnow()

        exists = Favorite.query.filter_by(open_id=open_id, frame_model=frame_model).first()
        if not exists:
            fav = Favorite(open_id=open_id, frame_model=frame_model, batch_id=batch_id, batch_time=batch_time)
            db.session.add(fav)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error adding favorite')


@app.route('/api/favorites', methods=['DELETE'])
def remove_favorite():
    """取消推荐。Body: { open_id, frame_model }"""
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
        # 合规性校验：长度与字符集（微信 openid 通常为长度较长的数字与字母，附加下划线）
        # 允许范围：a-zA-Z0-9-_，长度 6-64（经验值；如需放宽可调整）
        # 格式 + 长度校验：微信 openid 为 28 位（字母数字，下划线或破折号极少出现，这里宽松允许）
        if not re.fullmatch(r'[A-Za-z0-9_-]{28}', open_id):
            logger.error('INVALID_OPEN_ID format_or_length violation (expect length=28 alnum/_-): %r len=%d', open_id, len(open_id))
            # 不中断业务，如需强制可改为直接返回 400
            # return jsonify({'status': 'error', 'message': 'open_id invalid'}), 400
        # 冗余保护（理论不会触发，因为上面已限定 28）：
        if len(open_id) != 28:
            logger.error('INVALID_OPEN_ID length != 28: len=%d value=%r', len(open_id), open_id)

        nickname = (data.get('nickname') or '').strip() or None
        avatar_url = (data.get('avatar_url') or '').strip() or None
        referrer_open_id = (data.get('referrer_open_id') or '').strip() or None

        user = User.query.get(open_id)
        if not user:
            # 创建新用户时可带上 referrer_open_id
            if referrer_open_id == open_id:
                referrer_open_id = None  # 自己不能作为自己的介绍人
            new_user = User(open_id=open_id, nickname=nickname, avatar_url=avatar_url, referrer_open_id=referrer_open_id)
            db.session.add(new_user)
            try:
                db.session.commit()
                return jsonify({'status': 'success', 'data': new_user.to_dict()})
            except IntegrityError:
                db.session.rollback()
                # 并发创建导致冲突，重新获取用户并走更新逻辑
                user = User.query.get(open_id)
        
        # 仅当传入新值时更新
        if user:
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
        else:
            # 理论上不应到达此处
            return jsonify({'status': 'error', 'message': 'User not found after retry'}), 500
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error upserting user')

@app.route('/api/users/profile', methods=['GET'])
def get_user_profile():
    """获取用户基础资料（昵称与头像）。
    Query: open_id
    Return: { status, data: { open_id, nickname, avatar_url } } 若不存在返回 data 为 null。
    """
    try:
        open_id = (request.args.get('open_id') or '').strip()
        if not open_id:
            return jsonify({'status': 'error', 'message': 'open_id is required'}), 400
        user = User.query.get(open_id)
        if not user:
            return jsonify({'status': 'success', 'data': None})
        return jsonify({'status': 'success', 'data': {
            'open_id': user.open_id,
            'nickname': user.nickname or '',
            'avatar_url': user.avatar_url or ''
        }})
    except Exception as e:
        return handle_error(e, 'Error getting user profile')


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
            created_at=now_cn(),
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


# === 销售分享推送 & 打开记录 ===
@app.route('/api/shares/push', methods=['POST'])
def create_share_push():
    """销售发起一次分享推送。
    Body JSON: { salesperson_open_id: str, product_list: [str, ...], note?: str (0-10 chars) }
    返回创建的分享记录。
    规则：
    - salesperson_open_id 必填，必须在销售表中存在；
    - product_list 必填，至少一个型号，去重后存储；
    - 存储为 SalesShare 记录，初始 open_count=0，is_opened=False。
    """
    try:
        data = request.get_json(silent=True) or {}
        salesperson_open_id = (data.get('salesperson_open_id') or '').strip()
        products = data.get('product_list') or []
        dedup_key = (data.get('dedup_key') or '').strip()
        note = (data.get('note') or '').strip()
        try:
            logger.info('shares.push request sp=%s items=%s note_len=%s dedup_key=%r',
                        salesperson_open_id, (len(products) if isinstance(products, list) else 'NA'),
                        (len(note) if isinstance(note, str) else 0), dedup_key)
        except Exception:
            pass
        if not salesperson_open_id or not isinstance(products, list):
            return jsonify({'status': 'error', 'message': 'salesperson_open_id and product_list(list) are required'}), 400
        # 校验是否为销售
        sp = Salesperson.query.filter_by(open_id=salesperson_open_id).first()
        if not sp:
            return jsonify({'status': 'error', 'message': 'salesperson not found'}), 400
        # 产品列表去重 & 过滤空值；限制数量 50
        seen = set()
        clean = []
        for p in products:
            if not p or not isinstance(p, str):
                continue
            mm = p.strip()
            if not mm or mm in seen:
                continue
            seen.add(mm)
            clean.append(mm)
            if len(clean) >= 50:
                break
        if not clean:
            return jsonify({'status': 'error', 'message': 'product_list cannot be empty'}), 400
        # 备注长度限制（按字符计数，最多10）
        try:
            if len(note) > 10:
                note = note[:10]
        except Exception:
            note = note[:10] if note else None
        # 兼容性保护：仅当模型具备 dedup_key 属性时，启用去重逻辑
        has_dedup_attr = hasattr(SalesShare, 'dedup_key')
        # 若携带 dedup_key，先尝试按键查找，避免重复创建
        if dedup_key and has_dedup_attr:
            exist = SalesShare.query.filter_by(dedup_key=dedup_key).first()
            if exist:
                try:
                    logger.info('shares.push dedup-hit key=%r share_id=%s open_count=%s is_sent=%s',
                                dedup_key, getattr(exist, 'id', None), getattr(exist, 'open_count', None), getattr(exist, 'is_sent', None))
                except Exception:
                    pass
                return jsonify({'status': 'success', 'data': exist.to_dict(), 'dedup': True})
        rec_kwargs = {
            'salesperson_open_id': salesperson_open_id,
            'product_list': json.dumps(clean, ensure_ascii=False),
            'note': note or None,
            # 统一写入北京时间
            'push_time': now_cn(),
        }
        if has_dedup_attr:
            rec_kwargs['dedup_key'] = dedup_key or None
        rec = SalesShare(**rec_kwargs)
        db.session.add(rec)
        try:
            db.session.commit()
            try:
                logger.info('shares.push created id=%s sp=%s items=%s note=%r dedup_key=%r',
                            getattr(rec, 'id', None), salesperson_open_id, len(clean), (note or None), (dedup_key or None))
            except Exception:
                pass
        except Exception as ce:
            # 可能并发唯一冲突（若后续添加唯一索引），回退后重查
            db.session.rollback()
            if dedup_key and has_dedup_attr:
                exist2 = SalesShare.query.filter_by(dedup_key=dedup_key).first()
                if exist2:
                    try:
                        logger.info('shares.push dedup-collision key=%r resolved_to_id=%s', dedup_key, getattr(exist2, 'id', None))
                    except Exception:
                        pass
                    return jsonify({'status': 'success', 'data': exist2.to_dict(), 'dedup': True})
            raise ce
        return jsonify({'status': 'success', 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error creating share push')


@app.route('/api/shares/open', methods=['POST'])
def track_share_open():
    """记录客户打开某次分享。
    Body JSON: { share_id: int, customer_open_id: str }
    行为：
    - share_id 找不到返回 404
    - 若 customer_open_id 为空或非法返回 400
    - 去重：同一客户多次打开仅计一次；
    - 更新 open_count / is_opened / first_open_time / last_open_time / customer_open_ids。
    返回更新后的分享记录。
    """
    try:
        data = request.get_json(silent=True) or {}
        share_id = data.get('share_id')
        customer_open_id = (data.get('customer_open_id') or '').strip()
        if not isinstance(share_id, int):
            try:
                share_id = int(share_id)
            except Exception:
                share_id = None
        if not share_id or not customer_open_id:
            return jsonify({'status': 'error', 'message': 'share_id and customer_open_id are required'}), 400
        try:
            logger.info('shares.open request share_id=%s customer=%s', share_id, customer_open_id)
        except Exception:
            pass
        rec = SalesShare.query.get(share_id)
        if not rec:
            return jsonify({'status': 'error', 'message': 'share not found'}), 404
        try:
            existing = json.loads(rec.customer_open_ids) if rec.customer_open_ids else []
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        changed = False
        if customer_open_id not in existing:
            existing.append(customer_open_id)
            rec.customer_open_ids = json.dumps(existing, ensure_ascii=False)
            rec.open_count = len(existing)
            now = now_cn()
            if not rec.first_open_time:
                rec.first_open_time = now
            rec.last_open_time = now
            rec.is_opened = rec.open_count > 0
            changed = True
        if changed:
            db.session.commit()
            try:
                logger.info('shares.open updated share_id=%s customer=%s open_count=%s first_open_time=%s last_open_time=%s',
                            getattr(rec, 'id', None), customer_open_id, getattr(rec, 'open_count', None), getattr(rec, 'first_open_time', None), getattr(rec, 'last_open_time', None))
            except Exception:
                pass
        else:
            try:
                logger.info('shares.open duplicate-ignore share_id=%s customer=%s open_count=%s', getattr(rec, 'id', None), customer_open_id, getattr(rec, 'open_count', None))
            except Exception:
                pass
        return jsonify({'status': 'success', 'data': rec.to_dict(), 'updated': changed})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error tracking share open')


@app.route('/api/shares/open_by_dedup', methods=['POST'])
def track_share_open_by_dedup():
    """按 dedup_key 记录客户打开某次分享（用于未能携带 shid 的分享路径）。
    Body JSON: { dedup_key: str, customer_open_id: str }
    行为：
    - 若当前部署未启用 dedup_key 字段，则返回 400
    - dedup_key 未找到返回 404
    - 其余逻辑同 /api/shares/open：同一客户多次打开仅计一次，更新 open_count/is_opened 等
    """
    try:
        # 兼容性：仅当模型具备 dedup_key 属性时启用
        if not hasattr(SalesShare, 'dedup_key'):
            return jsonify({'status': 'error', 'message': 'dedup_key not supported on server'}), 400
        data = request.get_json(silent=True) or {}
        dedup_key = (data.get('dedup_key') or '').strip()
        customer_open_id = (data.get('customer_open_id') or '').strip()
        if not dedup_key or not customer_open_id:
            return jsonify({'status': 'error', 'message': 'dedup_key and customer_open_id are required'}), 400
        try:
            logger.info('shares.open_by_dedup request key=%r customer=%s', dedup_key, customer_open_id)
        except Exception:
            pass
        rec = SalesShare.query.filter_by(dedup_key=dedup_key).first()
        if not rec:
            return jsonify({'status': 'error', 'message': 'share not found by dedup_key'}), 404
        try:
            existing = json.loads(rec.customer_open_ids) if rec.customer_open_ids else []
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        changed = False
        if customer_open_id not in existing:
            existing.append(customer_open_id)
            rec.customer_open_ids = json.dumps(existing, ensure_ascii=False)
            rec.open_count = len(existing)
            now = now_cn()
            if not rec.first_open_time:
                rec.first_open_time = now
            rec.last_open_time = now
            rec.is_opened = rec.open_count > 0
            changed = True
        if changed:
            db.session.commit()
            try:
                logger.info('shares.open_by_dedup updated key=%r share_id=%s customer=%s open_count=%s first_open_time=%s last_open_time=%s',
                            dedup_key, getattr(rec, 'id', None), customer_open_id, getattr(rec, 'open_count', None), getattr(rec, 'first_open_time', None), getattr(rec, 'last_open_time', None))
            except Exception:
                pass
        else:
            try:
                logger.info('shares.open_by_dedup duplicate-ignore key=%r share_id=%s customer=%s open_count=%s',
                            dedup_key, getattr(rec, 'id', None), customer_open_id, getattr(rec, 'open_count', None))
            except Exception:
                pass
        return jsonify({'status': 'success', 'data': rec.to_dict(), 'updated': changed})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error tracking share open by dedup_key')


@app.route('/api/shares', methods=['GET'])
def list_shares():
    """列出分享推送记录，支持按销售或客户过滤。
    Query 参数：
      - salesperson_open_id: 仅列出该销售发起的分享
      - customer_open_id: 仅列出被该客户打开过的分享
      - page, per_page: 分页
    """
    try:
        salesperson_open_id = (request.args.get('salesperson_open_id') or '').strip()
        customer_open_id = (request.args.get('customer_open_id') or '').strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        try:
            logger.info('shares.list query sp=%s customer=%s page=%s per_page=%s',
                        salesperson_open_id or '-', customer_open_id or '-', page, per_page)
        except Exception:
            pass
        q = SalesShare.query
        if salesperson_open_id:
            q = q.filter(SalesShare.salesperson_open_id == salesperson_open_id)
        # 仅显示已发送的记录
        try:
            q = q.filter(SalesShare.is_sent.is_(True))
        except Exception:
            # 兼容性保护：若字段不可用则忽略
            pass
        if customer_open_id:
            # customer_open_ids 中包含该客户；使用 LIKE 简单匹配（JSON 数组字符串），再在内存中过滤精确包含
            like = f"%{customer_open_id}%"
            q = q.filter(SalesShare.customer_open_ids.like(like))
        items = paginate_query(q.order_by(SalesShare.id.desc()), page, per_page)
        data_items = [r.to_dict() for r in items.items]
        # 若使用 customer_open_id，需要精确过滤（避免 LIKE 误命中子串）
        if customer_open_id:
            data_items = [d for d in data_items if customer_open_id in (d.get('customer_open_ids') or [])]
        try:
            logger.info('shares.list result count=%s total=%s page=%s pages=%s',
                        len(data_items), items.total, items.page, items.pages)
        except Exception:
            pass
        return jsonify({'status': 'success', 'data': {
            'items': data_items,
            'total': items.total,
            'pages': items.pages,
            'current_page': items.page
        }})
    except Exception as e:
        return handle_error(e, 'Error listing shares')


@app.route('/api/shares/mark_sent', methods=['POST'])
def mark_share_sent():
    """标记分享记录已触发发送（分享面板展示）。
    Body: { share_id: int }
    行为：
      - 若 share_id 不存在返回 404
      - 更新 is_sent=true, sent_count+=1, last_sent_time=NOW()
    返回更新后的记录。
    注意：由于微信分享回调限制，这是近似统计发送尝试的辅助字段。
    """
    try:
        data = request.get_json(silent=True) or {}
        share_id = data.get('share_id')
        if not isinstance(share_id, int):
            try:
                share_id = int(share_id)
            except Exception:
                share_id = None
        if not share_id:
            return jsonify({'status': 'error', 'message': 'share_id is required'}), 400
        try:
            logger.info('shares.mark_sent request share_id=%s', share_id)
        except Exception:
            pass
        rec = SalesShare.query.get(share_id)
        if not rec:
            return jsonify({'status': 'error', 'message': 'share not found'}), 404
        rec.is_sent = True
        rec.sent_count = (rec.sent_count or 0) + 1
        rec.last_sent_time = now_cn()
        db.session.commit()
        try:
            logger.info('shares.mark_sent updated share_id=%s sent_count=%s last_sent_time=%s',
                        getattr(rec, 'id', None), getattr(rec, 'sent_count', None), getattr(rec, 'last_sent_time', None))
        except Exception:
            pass
        return jsonify({'status': 'success', 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error marking share sent')


@app.route('/api/favorites/batch', methods=['POST'])
def add_favorites_batch():
    """批量添加推荐。
    Body: { open_id: str, frame_models: [str, ...], reset?: bool }
    - 当 reset=true 且 open_id 为销售角色时：先清空该用户的推荐，再加入传入列表（替换推荐）。
    - 其他情况：保持原逻辑，幂等添加（忽略已存在）。
    忽略无效或未上架的商品；返回 { added: n, reset: bool }。
    """
    try:
        data = request.get_json(silent=True) or {}
        open_id = (data.get('open_id') or '').strip()
        items = data.get('frame_models') or []
        if not open_id or not isinstance(items, list):
            return jsonify({'status': 'error', 'message': 'open_id and frame_models(list) are required'}), 400

        # 是否请求重置推荐（仅对销售角色生效）
        reset_req = data.get('reset', False)
        if isinstance(reset_req, str):
            reset_req = reset_req.strip().lower() in ('1', 'true', 'yes', 'on')
        reset = bool(reset_req)

        # 确保用户存在
        user = User.query.get(open_id)
        if not user:
            user = User(open_id=open_id)
            db.session.add(user)

        # 若请求重置，需校验是否为销售；非销售则忽略 reset
        if reset:
            try:
                is_sales = Salesperson.query.filter_by(open_id=open_id).first() is not None
                if not is_sales:
                    reset = False
            except Exception:
                reset = False

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

        if reset and not uniq:
            # 重置但传空列表：清空推荐
            Favorite.query.filter_by(open_id=open_id).delete(synchronize_session=False)
            db.session.commit()
            return jsonify({'status': 'success', 'data': {'added': 0, 'reset': True}})
        if not uniq:
            return jsonify({'status': 'success', 'data': {'added': 0, 'reset': False}})

        # 查询有效商品
        valid = Product.query.with_entities(Product.frame_model).filter(Product.is_active == '是', Product.frame_model.in_(uniq)).all()
        valid_set = {row.frame_model for row in valid}

        added = 0
        # 新批次 ID：统一一个 batch_id 赋予本次新增的记录
        new_batch_id = int(time.time())
        batch_time = datetime.utcnow()
        if reset:
            # 替换推荐：清空后全量加入有效集合
            Favorite.query.filter_by(open_id=open_id).delete(synchronize_session=False)
            for fm in valid_set:
                db.session.add(Favorite(open_id=open_id, frame_model=fm, batch_id=new_batch_id, batch_time=batch_time))
                added += 1
        else:
            # 现有推荐（仅用于幂等添加场景）
            existing = Favorite.query.with_entities(Favorite.frame_model).filter(Favorite.open_id == open_id, Favorite.frame_model.in_(list(valid_set))).all()
            exist_set = {row.frame_model for row in existing}
            for fm in valid_set:
                if fm in exist_set:
                    continue
                db.session.add(Favorite(open_id=open_id, frame_model=fm, batch_id=new_batch_id, batch_time=batch_time))
                added += 1
        db.session.commit()
        return jsonify({'status': 'success', 'data': {'added': added, 'reset': bool(reset), 'batch_id': new_batch_id}})
    except Exception as e:
        db.session.rollback()
        return handle_error(e, 'Error adding favorites batch')


# === 简易后台（PC）数据查看 ===
def _admin_response(template_name, **context):
    """渲染管理页面并放宽 CSP 以允许样式/静态资源。"""
    html = render_template(template_name, **context)
    resp = make_response(html)
    # 覆盖默认 CSP，允许样式和本域静态资源
    resp.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self' 'unsafe-inline'"
    # PC 页面可缓存短期（如需禁用可改为 no-store）
    resp.headers.setdefault('Cache-Control', 'no-cache')
    return resp


@app.route('/admin', methods=['GET'])
def admin_home():
    return _admin_response('admin/index.html',
                           pv_action=url_for('admin_pageviews'),
                           ss_action=url_for('admin_sales_shares'))


@app.route('/admin/pageviews', methods=['GET'])
def admin_pageviews():
    open_id = (request.args.get('open_id') or '').strip()
    # 结果上下文
    user_info = None
    referrals = []
    referrals_count = 0
    fav_products = []
    pv_list = []

    def _is_private_ip(ip: str) -> bool:
        try:
            if not ip:
                return True
            ip = ip.strip()
            return (
                ip.startswith('10.') or
                ip.startswith('192.168.') or
                ip.startswith('127.') or
                ip.startswith('::1') or
                (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31)
            )
        except Exception:
            return False

    # 简单 UA 品牌提取
    def _ua_device(ua: str) -> str:
        if not ua:
            return ''
        u = ua.lower()
        if 'iphone' in u or 'ipad' in u or 'macintosh' in u or 'ios' in u:
            return 'iPhone/iOS'
        if 'huawei' in u or 'honor' in u or 'huaweibrowser' in u:
            return 'Huawei/Honor'
        if 'xiaomi' in u or 'redmi' in u or 'miui' in u:
            return 'Xiaomi/Redmi'
        if 'oppo' in u:
            return 'OPPO'
        if 'vivo' in u:
            return 'vivo'
        if 'oneplus' in u:
            return 'OnePlus'
        if 'samsung' in u or 'sm-' in u:
            return 'Samsung'
        if 'android' in u:
            return 'Android'
        if 'windows' in u:
            return 'Windows'
        if 'mac os' in u:
            return 'macOS'
        return ''

    # 简单 IP 定位（外网 IP），使用第三方服务，带缓存
    _IP_LOC_CACHE = {}
    def _ip_location(ip: str) -> str:
        try:
            if not ip or _is_private_ip(ip):
                return '内网IP'
            if ip in _IP_LOC_CACHE:
                return _IP_LOC_CACHE[ip]
            # 使用 ip-api.com（免费、限流）。生产可替换为内置库或自建服务。
            url = f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,regionName,city"
            r = requests.get(url, timeout=1.5)
            if r.ok:
                j = r.json() or {}
                if j.get('status') == 'success':
                    region = (j.get('regionName') or '').strip()
                    city = (j.get('city') or '').strip()
                    loc = (region + ' ' + city).strip()
                    _IP_LOC_CACHE[ip] = loc or ip
                    return _IP_LOC_CACHE[ip]
        except Exception:
            pass
        return ip or ''

    try:
        if not open_id:
            return _admin_response('admin/pageviews.html', open_id=open_id,
                                   user_info=None, referrals=[], referrals_count=0,
                                   fav_products=[], pv_list=[], preview_models=[])
        # 基本信息
        u = User.query.get(open_id)
        if u:
            sales_name = ''
            sales_open = (u.my_sales_open_id or '').strip()
            if sales_open:
                sp = Salesperson.query.filter_by(open_id=sales_open).first()
                if sp:
                    sales_name = sp.name or ''
            user_info = {
                'open_id': u.open_id,
                'nickname': u.nickname or '',
                'avatar_url': u.avatar_url or '',
                'created_at': u.created_at,
                'sales_open_id': sales_open,
                'sales_name': sales_name,
            }
        # 转介绍
        try:
            rs = (User.query
                  .with_entities(User.open_id, User.nickname, User.avatar_url, User.created_at)
                  .filter(User.referrer_open_id == open_id)
                  .order_by(User.created_at.desc())
                  .all())
            referrals = [{
                'open_id': r.open_id,
                'nickname': r.nickname or '',
                'avatar_url': r.avatar_url or '',
                'created_at': r.created_at,
            } for r in rs]
            referrals_count = len(referrals)
        except Exception:
            referrals = []
            referrals_count = 0
        # 推荐商品列表（去重、仅上架）
        try:
            subq = select(Favorite.frame_model).where(Favorite.open_id == open_id)
            prods = Product.query.filter(Product.frame_model.in_(subq), Product.is_active == '是').all()
            fav_products = [_serialize_product_with_public_images(p) for p in prods]
        except Exception:
            fav_products = []
        # 访问日志（最新 500 条）
        try:
            pv_rows = (PageView.query
                       .filter_by(open_id=open_id)
                       .order_by(PageView.created_at.desc())
                       .limit(500)
                       .all())
        except Exception as e:
            logger.error('admin pageviews query error: %s', e)
            pv_rows = []
        # 提取预览过的镜架型号：路径 /pages/watchlist/preview?model=XXX
        preview_models_set = set()
        from urllib.parse import urlparse, parse_qs
        for r in pv_rows:
            try:
                p = (r.page or '').strip()
                if p.startswith('/pages/watchlist/preview'):
                    q = urlparse(p)
                    qs = parse_qs(q.query or '')
                    m = (qs.get('model') or [''])[0].strip()
                    if m:
                        preview_models_set.add(m)
            except Exception:
                pass
        # 预取 IP 定位
        uniq_ips = []
        seen_ip = set()
        for r in pv_rows:
            ip = (r.ip or '').strip()
            if ip and ip not in seen_ip:
                seen_ip.add(ip)
                uniq_ips.append(ip)
        for ip in uniq_ips[:100]:  # 限制最多预查 100 个，避免阻塞
            _IP_LOC_CACHE.setdefault(ip, _ip_location(ip))
        # 组装最终列表
        pv_list = [{
            'time_str': to_beijing(r.created_at),
            'page': r.page,
            'ip': r.ip or '',
            'ip_loc': _IP_LOC_CACHE.get((r.ip or '').strip(), (r.ip or '')),
            'device': _ua_device(r.user_agent or ''),
            'user_agent': r.user_agent or ''
        } for r in pv_rows]
    except Exception as e:
        logger.error('admin pageviews build error: %s', e)
    return _admin_response('admin/pageviews.html',
                           open_id=open_id,
                           user_info=user_info,
                           referrals=referrals,
                           referrals_count=referrals_count,
                           fav_products=fav_products,
                           pv_list=pv_list,
                           preview_models=sorted(preview_models_set))


@app.route('/admin/sales_shares', methods=['GET'])
def admin_sales_shares():
    sales_open_id = (request.args.get('sales_open_id') or request.args.get('open_id') or '').strip()
    rows = []
    grouped = []
    sales_info = None
    if sales_open_id:
        try:
            q = SalesShare.query.filter(SalesShare.salesperson_open_id == sales_open_id).order_by(SalesShare.push_time.desc()).limit(1000)
            rows = q.all()
        except Exception as e:
            logger.error('admin sales_shares query error: %s', e)
            rows = []
        # 销售信息（包含用户昵称与头像）
        try:
            sp = Salesperson.query.filter_by(open_id=sales_open_id).first()
            usr = User.query.get(sales_open_id)
            sales_info = {
                'open_id': sales_open_id,
                'name': (sp.name if sp else ''),
                'nickname': (usr.nickname if usr else ''),
                'avatar_url': (usr.avatar_url if usr else ''),
                'user_created_at': (usr.created_at if usr else None)
            }
        except Exception:
            sales_info = {
                'open_id': sales_open_id,
                'name': '',
                'nickname': '',
                'avatar_url': '',
                'user_created_at': None
            }
        # 按推送日期分组（以数据库时间为准，约定已是北京时间）
        from collections import OrderedDict
        by_date = OrderedDict()
        for r in rows:
            dt = r.push_time or r.last_sent_time or r.first_open_time
            try:
                if not dt:
                    d = '未知日期'
                elif getattr(dt, 'tzinfo', None) is None:
                    d = dt.date().isoformat()
                else:
                    d = dt.astimezone(timezone(CN_UTC_OFFSET)).date().isoformat()
            except Exception:
                d = '未知日期'
            by_date.setdefault(d, []).append(r)
        grouped = [{'date': k, 'items': v} for k, v in by_date.items()]
    return _admin_response('admin/sales_shares.html', sales_open_id=sales_open_id, grouped=grouped, sales_info=sales_info)

if __name__ == '__main__':
    # 仅用于开发。生产请使用 WSGI 服务器（如 gunicorn/uwsgi/waitress）并在反向代理后运行
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = app.config.get('DEBUG', False)
    app.run(debug=debug, host=host, port=port)