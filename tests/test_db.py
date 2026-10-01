r"""
======================================================================
test_db.py —— Day2 验收测试（数据库封装层）
======================================================================
运行方式（推荐在项目根目录执行）：
    .venv\Scripts\python.exe -m tests.test_db
（也可以直接 .venv\Scripts\python.exe tests\test_db.py，脚本会自动把项目根加入搜索路径）

验收 4 项：
    ① 连接测试      ② 保存故事      ③ 按关键词查询      ④ 对话历史 + 会话列表
"""
import sys
from pathlib import Path

# 把"项目根目录"加入模块搜索路径，保证无论怎么运行这个脚本都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.db_util import DBUtil

# ① 连接测试
print("连接测试：", DBUtil.test_connection())

# ② 保存一篇故事
DBUtil.save_story(
    session_id="test_session_001",
    story_title="测试故事",
    main_role="小鸟",
    age_group="3-6岁",
    story_content="小鸟学会了帮助朋友。",
    moral="助人为乐",
)
print("保存成功！")

# ③ 按关键词查出来
for s in DBUtil.get_all_stories(keyword="测试"):
    print(f"查到：{s['story_title']}｜主角{s['main_role']}｜{s['create_time']}")

# ④ 保存对话并查询会话列表
DBUtil.save_chat_history("test_session_001", "写个故事", "好的！")
print(DBUtil.get_all_sessions())
