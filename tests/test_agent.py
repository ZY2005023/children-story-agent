r"""
======================================================================
test_agent.py —— Day4 验收测试（智能体端到端）
======================================================================
运行方式（推荐在项目根目录执行）：
    .venv\Scripts\python.exe -m tests.test_agent
（也可以直接 .venv\Scripts\python.exe tests\test_agent.py，脚本会自动把项目根加入搜索路径）

【课堂节奏】
第一轮跑的时候，盯着终端滚动输出的 verbose 日志，
对照 ReAct 三步找 Thought / Action / Observation / Final Answer，
然后打开 MySQL 确认故事真的存进去了：
    SELECT * FROM children_story ORDER BY id DESC LIMIT 1;
"""
import sys
from pathlib import Path

# 把"项目根目录"加入模块搜索路径，保证无论怎么运行这个脚本都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.agent_service import chat, set_current_session

set_current_session("test_session_004")

print("=" * 60)
print("【第一轮】创作一个关于勇敢的小兔子的故事，适合3-6岁，教育孩子不要害怕黑暗")
print("=" * 60)
result = chat("创作一个关于勇敢的小兔子的故事，适合3-6岁，教育孩子不要害怕黑暗")
print("\n>>> 最终回答：\n", result["output"])
print("\n>>> 工具调用步骤数：", len(result["intermediate_steps"]))

print("\n" + "=" * 60)
print("【第二轮】把主角改成小刺猬（验证多轮记忆）")
print("=" * 60)
result2 = chat("把主角改成小刺猬", "")
print("\n>>> 最终回答：\n", result2["output"])
