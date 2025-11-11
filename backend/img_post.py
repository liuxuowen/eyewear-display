from PIL import Image
import os

# ======= 配置部分 =======
input_dir = r"/var/www/resource/products_img"   # 原始图片目录
output_dir = r"/var/www/resource/products_img_post"  # 输出目录

max_size = 1000  # 最大边的上限（像素）
# =======================

# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

# 支持的图片格式
valid_exts = ('.jpg', '.jpeg', '.png')

for filename in os.listdir(input_dir):
    if not filename.lower().endswith(valid_exts):
        continue

    input_path = os.path.join(input_dir, filename)
    output_path = os.path.join(output_dir, filename)

    try:
        with Image.open(input_path) as img:
            width, height = img.size
            max_dim = max(width, height)

            if max_dim > max_size:
                scale = max_size / max_dim
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"Resized {filename}: {width}x{height} → {new_width}x{new_height}")
            else:
                print(f"Skipped {filename}: {width}x{height}")

            # 保存
            img.save(output_path)
    except Exception as e:
        print(f"Error processing {filename}: {e}")

print("✅ 所有图片处理完成！")
