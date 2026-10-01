-- =====================================================================
-- init.sql —— 数据库初始化脚本（儿童故事创作智能体）
-- =====================================================================
-- 【作用】一次性完成：建库 + 建两张表 + 插入 2 条演示数据
--
-- 【执行方式】两种任选（在项目根目录打开终端）：
--   方式一（命令行）：
--     mysql -uroot -p < sql/init.sql
--   方式二（Navicat）：右键连接 -> 运行 SQL 文件 -> 选择本文件
--
-- 【验证方式】
--   mysql -uroot -p
--   mysql> use children_story_db;
--   mysql> select id, story_title, main_role, age_group from children_story;
--
-- 【说明】脚本可重复执行：
--   - 建库建表用 IF NOT EXISTS，不会报错
--   - 演示数据用 WHERE NOT EXISTS 做去重，不会重复插入
-- =====================================================================

-- ---------------------------------------------------------------------
-- 第 1 步：创建数据库
-- ---------------------------------------------------------------------
-- 字符集必须 utf8mb4：才能正确存储中文和 emoji（utf8 存不了 emoji）
CREATE DATABASE IF NOT EXISTS children_story_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE children_story_db;

-- ---------------------------------------------------------------------
-- 第 2 步：创建【对话历史表】knowledge_chat_history
-- ---------------------------------------------------------------------
-- 对应 db_util.py 的三个方法：
--   save_chat_history()  -> INSERT
--   get_chat_history()   -> SELECT ... WHERE session_id = ? ORDER BY id DESC
--   get_all_sessions()   -> GROUP BY session_id + MAX(create_time) + COUNT(*)
--
-- session_id：同一轮多轮对话共用一个 ID，用来把消息串成一次会话
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_chat_history (
    id          INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    session_id  VARCHAR(64)  NOT NULL COMMENT '会话ID（同一轮多轮对话共用）',
    user_query  TEXT         NOT NULL COMMENT '用户提问内容',
    ai_answer   MEDIUMTEXT            COMMENT 'AI 回答内容（故事可能较长，用 MEDIUMTEXT）',
    create_time DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_session_id (session_id),
    INDEX idx_create_time (create_time)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = '多轮对话历史表';

-- ---------------------------------------------------------------------
-- 第 3 步：创建【儿童故事表】children_story
-- ---------------------------------------------------------------------
-- 对应 db_util.py 的两个方法：
--   save_story()      -> INSERT（6 个字段）
--   get_all_stories() -> SELECT *，keyword 非空时 story_title LIKE '%关键词%'
--
-- 这条表就是"智能体自己存档"的结果：Agent 写完故事后调用
-- story_db_tool(action="save") 把故事落到这里
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS children_story (
    id            INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    session_id    VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '故事属于哪个会话',
    story_title   VARCHAR(255) NOT NULL COMMENT '故事标题',
    main_role     VARCHAR(100) DEFAULT '' COMMENT '主角名字',
    age_group     VARCHAR(50)  DEFAULT '' COMMENT '适合年龄段，如 3-6岁',
    story_content MEDIUMTEXT   NOT NULL COMMENT '故事完整正文',
    moral         VARCHAR(255) DEFAULT '' COMMENT '教育寓意',
    create_time   DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '保存时间',
    INDEX idx_session_id (session_id),
    INDEX idx_story_title (story_title),
    INDEX idx_create_time (create_time)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = '儿童故事表（Agent 自动存档）';

-- ---------------------------------------------------------------------
-- 第 4 步：插入 2 条演示数据（用于验收侧边栏"历史故事"面板）
-- ---------------------------------------------------------------------
-- 用 WHERE NOT EXISTS 保证重复执行本脚本时不会插入重复数据

INSERT INTO children_story
    (session_id, story_title, main_role, age_group, story_content, moral)
SELECT 'demo_session_001',
       '小兔子学会分享',
       '小兔子朵朵',
       '3-6岁',
       '在一片绿油油的草地上，住着一只叫朵朵的小兔子。朵朵有一根又大又甜的胡萝卜，她本来想自己一个人慢慢吃。这时，小刺猬球球和小松鼠跳跳走了过来，肚子饿得咕咕叫。朵朵看了看手里的胡萝卜，又看了看好朋友们的肚子，心里想："如果只有我一个人吃，好像也没那么甜了。"于是她把胡萝卜掰成了三份，一人一份。奇怪的是，朵朵觉得自己的那一份比原来更甜了。小刺猬和小松鼠开心地围着朵朵转圈圈，说："朵朵，你真好！"从那以后，三个好朋友每天一起找食物，一起分享，草地上的笑声越来越多。',
       '分享不会让快乐变少，反而会让快乐加倍。'
WHERE NOT EXISTS (
    SELECT 1 FROM children_story WHERE story_title = '小兔子学会分享'
);

INSERT INTO children_story
    (session_id, story_title, main_role, age_group, story_content, moral)
SELECT 'demo_session_002',
       '小乌龟慢慢上学记',
       '小乌龟慢慢',
       '7-9岁',
       '小乌龟慢慢要去河对岸的森林小学上学了。路上有一条长长的上坡路，小兔子蹦蹦几下就跳到了山顶，回头喊："慢慢，你太慢啦！"慢慢没有生气，也没有着急，他一步一步地往前爬，累了就歇一会儿，然后接着爬。太阳从东边升到了头顶，又从头顶慢慢滑向西边，慢慢终于爬到了山顶。站在山顶上，他看见了一条从没见过的美丽河流，还有一群正在等他一起上学的同学。老师说："慢慢，你虽然走得慢，但你从来没有停下来。"慢慢笑了，他知道自己一定会到达想去的地方。',
       '坚持不懈，比一时的快慢更重要。'
WHERE NOT EXISTS (
    SELECT 1 FROM children_story WHERE story_title = '小乌龟慢慢上学记'
);

-- ---------------------------------------------------------------------
-- 第 5 步：执行结果自检（在命令行会打印出来）
-- ---------------------------------------------------------------------
SELECT '数据库 children_story_db 初始化完成' AS 提示信息;
SELECT COUNT(*) AS 故事表记录数 FROM children_story;
SELECT COUNT(*) AS 对话历史表记录数 FROM knowledge_chat_history;
