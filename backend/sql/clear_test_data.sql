-- 清除测试数据脚本（MySQL）
-- 目标：清空除 `products` 表外的所有业务表数据，便于测试重启。
-- 当前涉及的表：users, page_views, favorites, sales
-- 注意：执行后将清空用户、访问记录、推荐与销售名单。
--       如果你需要保留 sales（销售白名单），请手动注释掉对应的 TRUNCATE 行。

SET FOREIGN_KEY_CHECKS = 0;

-- 建议优先清空从表（有外键指向 users/products 的表）
TRUNCATE TABLE `favorites`;
TRUNCATE TABLE `page_views`;

-- 再清空主表
TRUNCATE TABLE `users`;

SET FOREIGN_KEY_CHECKS = 1;

-- 备选方案（无 TRUNCATE 权限时可使用，记得先禁用外键检查）：
-- DELETE FROM `favorites`;
-- DELETE FROM `page_views`;
-- DELETE FROM `users`;
-- DELETE FROM `sales`;
