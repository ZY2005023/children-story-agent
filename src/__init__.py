"""
src —— 项目源码包

目录结构：
    src/config.py          全局配置（读 .env，集中管理所有可调参数）
    src/core/              业务核心层
        agent_service.py   智能体（LangChain Agent + 工具调用 + 流式输出）
        rag_service.py     RAG 知识库（切分 / 向量化 / FAISS 检索）
        db_util.py         MySQL 数据访问工具类
    src/ui/                界面层
        clarify_form.py    需求澄清问卷组件

启动入口在项目根目录的 app.py。
"""
