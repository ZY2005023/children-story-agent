"""
core —— 业务核心层

agent_service.py   智能体：提示词编排、工具注册（RAG 检索 / 故事存档）、
                   意图识别、创作变奏、多轮记忆、流式输出
rag_service.py     RAG：txt 素材加载 → 文本切分 → 向量化 → FAISS 建库 / 检索
db_util.py         MySQL：会话、聊天记录、故事内容的读写
"""
