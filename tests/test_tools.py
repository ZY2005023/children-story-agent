r"""
======================================================================
test_tools.py —— 先测工具，再测 Agent（分而治之的调试思路）
======================================================================
运行方式（推荐在项目根目录执行）：
    .venv\Scripts\python.exe -m tests.test_tools
（也可以直接 .venv\Scripts\python.exe tests\test_tools.py，脚本会自动把项目根加入搜索路径）

【重要细节（必讲）】
@tool 装饰之后，函数变成了 StructuredTool 对象，
测试时要用 .invoke({...}) 调用，参数用字典传 ——
这是学生最容易困惑的地方（直接 f(...) 会报 object is not callable）。
"""
import sys
from pathlib import Path

# 把"项目根目录"加入模块搜索路径，保证无论怎么运行这个脚本都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.agent_service import story_material_search, story_db_tool, set_current_session

set_current_session("test_session_004")

print("===== 测试工具1：RAG 检索 =====")
print(story_material_search.invoke({"query": "分享"}))   # 注意：工具对象要用 .invoke 调用

print("\n===== 测试工具2：保存 =====")
print(story_db_tool.invoke({
    "action": "save",
    "story_title": "课堂测试故事",
    "main_role": "小海豚",
    "age_group": "3-6岁",
    "story_content": "小海豚帮朋友找到回家的路。",
    "moral": "乐于助人",
}))

print("\n===== 测试工具2：查询 =====")
print(story_db_tool.invoke({"action": "query"}))
