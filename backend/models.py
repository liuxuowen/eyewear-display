from flask_sqlalchemy import SQLAlchemy

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
        #print("to_dict" + self.frame_model)
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
        #print(result['images'])   
        return result