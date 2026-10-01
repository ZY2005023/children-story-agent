r"""
======================================================================
test_rag.py —— Day3 验收测试（RAG 知识库）
======================================================================
运行方式（推荐在项目根目录执行）：
    .venv\Scripts\python.exe -m tests.test_rag
（也可以直接 .venv\Scripts\python.exe tests\test_rag.py，脚本会自动把项目根加入搜索路径）

验收要点：
    测试1「关于分享的故事」应命中《彩虹色的分享》
    测试2「坚持不懈」    应命中《小乌龟慢慢上学记》
    并观察相似度分数 —— 分数越小越相关（FAISS 默认 L2 距离）
"""
import sys
from pathlib import Path

# 把"项目根目录"加入模块搜索路径，保证无论怎么运行这个脚本都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import rag_service

# ① 构建（第一次跑会下载 Embedding 模型，之后秒级完成）
count = rag_service.build_vector_store()
print(f"✅ 知识库构建完成，共 {count} 个片段")

# ② 检索测试 1：语义相关（问题里没有原文的字，也能命中！）
print("\n===== 检索：关于分享的故事 =====")
print(rag_service.retrieve("关于分享的故事"))

# ③ 检索测试 2：坚持不懈
print("\n===== 检索：坚持不懈 =====")
print(rag_service.retrieve("坚持不懈"))

# ④ 检索测试 3：完全不相关（观察"没有结果"的提示）
print("\n===== 检索：宇宙飞船 =====")
print(rag_service.retrieve("宇宙飞船"))
