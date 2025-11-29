from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

db = SQLAlchemy()

class Product(db.Model):
    __tablename__ = 'products'
    
    frame_model = db.Column(db.String(100), primary_key=True, comment='镜架型号')
    is_active = db.Column(db.String(10), nullable=False, default='是', comment='商品是否有效')
    lens_size = db.Column(db.Float, nullable=False, comment='镜片大小(mm)')
    nose_bridge_width = db.Column(db.Float, nullable=False, comment='鼻梁宽度(mm)')
    temple_length = db.Column(db.Float, nullable=False, comment='镜腿长度(mm)')
    frame_total_length = db.Column(db.Float, nullable=False, comment='镜架总长(mm)')
    frame_height = db.Column(db.Float, nullable=False, comment='镜架高度(mm)')
    frame_material = db.Column(db.String(100), nullable=False, comment='镜架材料')
    weight = db.Column(db.Float, nullable=False, comment='重量(g)')
    price = db.Column(db.Float, nullable=False, comment='售价(元)')
    
    # 图片字段
    image1 = db.Column(db.Text, nullable=True, comment='图片1')
    image2 = db.Column(db.Text, nullable=True, comment='图片2')
    image3 = db.Column(db.Text, nullable=True, comment='图片3')
    image4 = db.Column(db.Text, nullable=True, comment='图片4')
    image5 = db.Column(db.Text, nullable=True, comment='图片5')
    image6 = db.Column(db.Text, nullable=True, comment='图片6')
    image7 = db.Column(db.Text, nullable=True, comment='图片7')
    image8 = db.Column(db.Text, nullable=True, comment='图片8')
    image9 = db.Column(db.Text, nullable=True, comment='图片9')
    image10 = db.Column(db.Text, nullable=True, comment='图片10')
    image11 = db.Column(db.Text, nullable=True, comment='图片11')
    image12 = db.Column(db.Text, nullable=True, comment='图片12')
    image13 = db.Column(db.Text, nullable=True, comment='图片13')
    image14 = db.Column(db.Text, nullable=True, comment='图片14')
    image15 = db.Column(db.Text, nullable=True, comment='图片15')
    
    brand = db.Column(db.String(100), nullable=True, comment='所属品牌')
    frame_thickness = db.Column(db.Float, nullable=True, comment='包边厚度(mm)')
    notes = db.Column(db.String(500), nullable=True, comment='备注信息')
    
    def to_dict(self):
        result = {
            'frame_model': self.frame_model,
            'lens_size': self.lens_size,
            'nose_bridge_width': self.nose_bridge_width,
            'temple_length': self.temple_length,
            'frame_total_length': self.frame_total_length,
            'frame_height': self.frame_height,
            'frame_material': self.frame_material,
            'weight': self.weight,
            'price': self.price,
            'brand': self.brand,
            'frame_thickness': self.frame_thickness,
            'notes': self.notes,
            'images': []
        }
        
        # 收集所有非空图片
        for i in range(1, 16):
            image = getattr(self, f'image{i}')
            if image:
                # 拼接为完整 URL
                result['images'].append(f"{image}")
        return result


class User(db.Model):
    __tablename__ = 'users'

    # 以微信 open_id 作为主键
    open_id = db.Column(db.String(64), primary_key=True, comment='微信 open_id')
    nickname = db.Column(db.String(100), nullable=True, comment='昵称')
    avatar_url = db.Column(db.String(255), nullable=True, comment='头像 URL')
    # 介绍人 open_id，可为空
    referrer_open_id = db.Column(db.String(64), nullable=True, index=True, comment='介绍人 open_id')
    # 我的销售 open_id，可为空
    my_sales_open_id = db.Column(db.String(64), nullable=True, index=True, comment='我的销售 open_id')
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        return {
            'open_id': self.open_id,
            'nickname': self.nickname,
            'avatar_url': self.avatar_url,
            'referrer_open_id': self.referrer_open_id,
            'my_sales_open_id': self.my_sales_open_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class PageView(db.Model):
    __tablename__ = 'page_views'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    open_id = db.Column(db.String(64), db.ForeignKey('users.open_id'), index=True, nullable=False)
    page = db.Column(db.String(255), nullable=False, comment='页面路径或标识')
    referer = db.Column(db.String(512), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    # 关系（可选）
    user = db.relationship('User', backref=db.backref('page_views', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'open_id': self.open_id,
            'page': self.page,
            'referer': self.referer,
            'user_agent': self.user_agent,
            'ip': self.ip,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Favorite(db.Model):
    __tablename__ = 'favorites'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    open_id = db.Column(db.String(64), db.ForeignKey('users.open_id'), index=True, nullable=False)
    frame_model = db.Column(db.String(100), db.ForeignKey('products.frame_model'), index=True, nullable=False)
    # 新增：推荐批次（同一批次内的记录共享相同 batch_id 与 batch_time）
    batch_id = db.Column(db.Integer, nullable=True, index=True, comment='推荐批次编号（按用户递增）')
    batch_time = db.Column(db.DateTime, nullable=True, comment='该批次的时间标记（同一批次统一时间）')
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('open_id', 'frame_model', name='uq_fav_user_model'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'open_id': self.open_id,
            'frame_model': self.frame_model,
            'batch_id': self.batch_id,
            'batch_time': self.batch_time.isoformat() if self.batch_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Salesperson(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    open_id = db.Column(db.String(64), unique=True, index=True, nullable=False, comment='销售微信 open_id')
    name = db.Column(db.String(100), nullable=False, comment='销售姓名')

    def to_dict(self):
        return {
            'id': self.id,
            'open_id': self.open_id,
            'name': self.name,
        }


class SalesShare(db.Model):
    """记录销售发起的分享推送，以及被客户打开的情况。
    设计说明：
    - salesperson_open_id: 推送发起人（销售）open_id，引用 sales.open_id（不使用外键约束以减少迁移复杂度）。
    - product_list: JSON 数组字符串，存储推送的镜架型号列表（frame_model）。
    - push_time: 发起时间。
    - customer_open_ids: JSON 数组字符串，记录已打开该分享的客户 open_id（去重）。
    - open_count: 已打开的唯一客户数量（从 customer_open_ids 去重长度计算，但为查询效率存储冗余字段）。
    - first_open_time / last_open_time: 首次/最近一次打开时间。
    - is_opened: 是否至少被打开过一次（open_count > 0 冗余标记）。
    """
    __tablename__ = 'sales_shares'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    salesperson_open_id = db.Column(db.String(64), index=True, nullable=False, comment='销售 open_id')
    product_list = db.Column(db.Text, nullable=False, comment='JSON 数组：推送的产品型号列表')
    push_time = db.Column(db.DateTime, server_default=func.now(), nullable=False, comment='推送时间')
    customer_open_ids = db.Column(db.Text, nullable=True, comment='JSON 数组：已打开的客户 open_id 列表')
    open_count = db.Column(db.Integer, nullable=False, default=0, comment='唯一打开客户数量')
    first_open_time = db.Column(db.DateTime, nullable=True, comment='首次打开时间')
    last_open_time = db.Column(db.DateTime, nullable=True, comment='最近一次打开时间')
    is_opened = db.Column(db.Boolean, nullable=False, default=False, comment='是否至少被打开过一次')
    # 发送状态：用于统计真正进入分享发送流程（受限于微信 API，无法100%确认对方收到，但可记录发送尝试）
    is_sent = db.Column(db.Boolean, nullable=False, default=False, comment='是否已触发发送（分享面板）')
    sent_count = db.Column(db.Integer, nullable=False, default=0, comment='触发发送次数')
    last_sent_time = db.Column(db.DateTime, nullable=True, comment='最近一次触发发送时间')
    note = db.Column(db.String(64), nullable=True, comment='分享备注（0-10字符）')
    # 去重键：由(销售open_id, 去重后的产品列表, 备注)确定，便于前后端幂等创建
    dedup_key = db.Column(db.String(128), nullable=True, unique=False, index=True, comment='前端/服务端计算的幂等键')

    def to_dict(self):
        import json
        try:
            products = json.loads(self.product_list) if self.product_list else []
            if not isinstance(products, list):
                products = []
        except Exception:
            products = []
        try:
            customer_ids = json.loads(self.customer_open_ids) if self.customer_open_ids else []
            if not isinstance(customer_ids, list):
                customer_ids = []
        except Exception:
            customer_ids = []
        return {
            'id': self.id,
            'salesperson_open_id': self.salesperson_open_id,
            'product_list': products,
            'push_time': self.push_time.isoformat() if self.push_time else None,
            'customer_open_ids': customer_ids,
            'open_count': self.open_count,
            'first_open_time': self.first_open_time.isoformat() if self.first_open_time else None,
            'last_open_time': self.last_open_time.isoformat() if self.last_open_time else None,
            'is_opened': self.is_opened,
            'is_sent': self.is_sent,
            'sent_count': self.sent_count,
            'last_sent_time': self.last_sent_time.isoformat() if self.last_sent_time else None,
            'note': self.note,
        }