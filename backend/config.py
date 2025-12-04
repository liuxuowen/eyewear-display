import os
from datetime import timedelta

class Config:
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql+pymysql://user:password@localhost:21079/eyewear')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 更健壮的连接池设置（避免长连接断开导致的 2006 MySQL has gone away 等问题）
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '280')),
        'pool_size': int(os.getenv('DB_POOL_SIZE', '5')),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '10')),
    }
    
    # API配置
    JSON_AS_ASCII = False  # 支持中文
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')  # JWT密钥
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)  # token有效期1天

    # 运行环境
    ENV = os.getenv('APP_ENV', 'development')  # development / production / staging
    DEBUG = os.getenv('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes', 'on')
    # 业务生产模式开关（控制UI展示等业务逻辑，与 ENV 区分）
    # 默认为 False (非生产模式)，如需开启请在 .env 设置 IS_PRODUCTION_MODE=true
    IS_PRODUCTION_MODE = os.getenv('IS_PRODUCTION_MODE', 'false').lower() in ('1', 'true', 'yes', 'on')
    # 客户推荐功能开关（控制非销售角色是否显示推荐好友入口）
    # 默认为 True (显示)，如需关闭请在 .env 设置 ENABLE_CUSTOMER_REFERRALS=false
    ENABLE_CUSTOMER_REFERRALS = os.getenv('ENABLE_CUSTOMER_REFERRALS', 'true').lower() in ('1', 'true', 'yes', 'on')

    # CORS 允许的来源，逗号分隔
    CORS_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*')
    # 请求体大小限制（默认 2MB）
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(2 * 1024 * 1024)))
    # 强制 HTTPS（位于反向代理/负载均衡启用 TLS 时，建议开启）
    FORCE_HTTPS = os.getenv('FORCE_HTTPS', '0').lower() in ('1', 'true', 'yes', 'on')
    PREFERRED_URL_SCHEME = 'https'
    # Cookie 安全（即便当前未使用 session，预先设定更安全的默认值）
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    
    # 微信小程序配置
    WECHAT_APPID = os.getenv('WECHAT_APPID', '')
    WECHAT_SECRET = os.getenv('WECHAT_SECRET', '')
    
    # 图片文件配置
    IMAGE_SAVE_DIR = os.getenv('IMAGE_SAVE_DIR', 'D:/data/eyewear/images')
    IMAGE_URL_PREFIX = os.getenv('IMAGE_URL_PREFIX', '/static/images/')

    # 搜索配置
    ALLOWED_SEARCH_FIELDS = [
        'frame_model',
        'lens_size',
        'nose_bridge_width',
        'temple_length',
        'frame_total_length',
        'frame_height',
        'weight',
        'price',
        'frame_material',
        'other_info',  # 模糊匹配 brand/notes（保留）
        'brand_info',  # 品牌信息（仅匹配 brand）
    ]
    DEFAULT_SEARCH_FIELD = os.getenv('DEFAULT_SEARCH_FIELD', 'frame_model')

    # （已废弃）销售白名单参数：现已改为从数据库 sales 表读取，不再使用该配置。
    SALES_OPENID_WHITELIST = []