import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from models import db, Product
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config.from_object(Config)

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

        products = paginate_query(Product.query.filter_by(is_active='是'), page, per_page)

        return jsonify({
            'status': 'success',
            'data': {
                'items': [product.to_dict() for product in products.items],
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
            'data': product.to_dict()
        })
    except Exception as e:
        return handle_error(e, f"Error getting product {frame_model}")

if __name__ == '__main__':
    # 仅用于开发。生产请使用 WSGI 服务器（如 gunicorn/uwsgi/waitress）并在反向代理后运行
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = app.config.get('DEBUG', False)
    app.run(debug=debug, host=host, port=port)