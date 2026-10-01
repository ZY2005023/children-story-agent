"""
======================================================================
rag_service.py —— RAG 向量知识库服务（新手入门第 3 课）
======================================================================

【一句话目标】
让智能体"会查资料"：把素材库里的儿童故事变成可检索的向量知识库，
用户提问时先检索出最相关的片段，塞进提示词给大模型参考。

【RAG 是什么？】
RAG = Retrieval-Augmented Generation（检索增强生成），分两步：
  - 离线准备（R）：把素材故事预处理成向量，存进 FAISS 向量库
  - 在线回答（A+G）：用户提问 -> 检索最相关片段 -> 塞进提示词 -> 大模型创作
类比：考场开卷考试。素材库就是"资料"，检索就是"翻书"，大模型是"答题的同学"。

【向量 / Embedding 大白话】
计算机不认识"勇敢""分享"是什么意思，它只认识数字。
Embedding 模型把一段话变成一串数字（向量），含义越接近的句子，
在数学空间里距离就越近。所以"检索相关素材"= 找距离最近的片段 = 纯数学计算。

【RAG 四步流水线】
  素材 txt 文件
    第 1 步 文档加载：TextLoader 把文件读成 Document 对象
                      （page_content=正文，metadata=来源）
    第 2 步 文本切分：切成小块 chunk（每块 CHUNK_SIZE 字，重叠 CHUNK_OVERLAP）
    第 3 步 向量化：  Embedding 模型把每块文字变成一串数字
    第 4 步 存 FAISS：向量库保存到磁盘（重启不用重建）
    检索：把问题也向量化 -> 算距离 -> 返回最相似的 top_k 块

【本项目用的 Embedding 模型】
BAAI/bge-small-zh-v1.5 —— 轻量中文模型，CPU 就能跑，首次使用自动下载约 100MB。
国内下载慢时用镜像：HF_ENDPOINT=https://hf-mirror.com（本文件已自动设置）

【懒加载（重点设计）】
Embedding 模型和向量库都很"重"（内存占用大、创建慢），
原则上要用的时候才创建，创建一次之后反复使用。
实现方式：模块级全局变量 + 判断是否为 None 才创建。

【模块级全局变量 + global 声明（重点，不写会报错）】
函数内部要修改模块级变量，必须先写 `global 变量名`，
否则 Python 会把它当成"函数内的局部变量"，导致赋值无效或报 UnboundLocalError。
"""
import os
import contextlib
from pathlib import Path

# 让 HuggingFace 从国内镜像下载模型，必须在导入 huggingface 相关库之前设置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from src import config                                     # 全局配置
from langchain_community.document_loaders import TextLoader        # 第1步 文档加载器
from langchain_community.vectorstores import FAISS                 # 第4步 向量库
from langchain_huggingface import HuggingFaceEmbeddings            # 第3步 Embedding 模型
from langchain_text_splitters import RecursiveCharacterTextSplitter  # 第2步 文本切分器

# ======================================================================
# 模块级全局变量：供整个文件使用，避免重复创建（懒加载的载体）
# ======================================================================
_embeddings_model = None   # Embedding 模型缓存：初次使用时创建，之后反复复用
_vector_store = None       # FAISS 向量库缓存：构建或加载后复用


# ======================================================================
# 【Windows 特有的坑】faiss 只能读写"相对路径"，必须特殊处理
# ======================================================================
# faiss 底层是 C++ 实现，在 Windows 上打不开带盘符的绝对路径
# （报错形如：could not open C:\...\index.faiss for writing: No such file or directory），
# 只接受 "data/faiss_index" 这种相对路径。
# 所以读写索引时，先临时把工作目录切到项目根目录，用完再切回来。
@contextlib.contextmanager
def _in_project_root():
    """临时把工作目录切到项目根目录（配合 faiss 对相对路径的要求）"""
    original = os.getcwd()
    os.chdir(config.BASE_DIR)
    try:
        yield
    finally:
        os.chdir(original)


def _faiss_index_rel() -> str:
    """把向量库目录转成"相对项目根目录"的路径字符串，专供 faiss 读写使用。
    config.FAISS_INDEX_PATH 是绝对路径（给 Python 侧用，如 mkdir / 判断文件存在）；
    faiss 侧则必须用这个相对路径版本。
    """
    return os.path.relpath(config.FAISS_INDEX_PATH, config.BASE_DIR).replace("\\", "/")


# ======================================================================
# 函数 1：get_embeddings —— 获取 Embedding 模型（懒加载）
# ======================================================================
def get_embeddings():
    """功能：获取 Embedding 模型（第一次调用时下载并创建，之后复用同一个对象）
    入参：无
    返回：embeddings —— 可调用 embed_query() 把文字转成向量的模型对象
    使用场景：构建向量库和检索时都会用到；懒加载保证网页启动速度不受影响
    """
    global _embeddings_model            # 声明要修改模块级变量（不写会报错）
    if _embeddings_model is None:       # 第一次调用：还没创建过
        # 创建 HuggingFace 的 Embedding 模型
        _embeddings_model = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,          # 模型名（bge-small-zh-v1.5）
            model_kwargs={"device": "cpu"},              # 用 CPU 跑，够用且不挑显卡
            encode_kwargs={"normalize_embeddings": True},# 归一化：让相似度计算更稳定
        )
    return _embeddings_model


# ======================================================================
# 函数 2：list_material_files —— 列出素材目录里的 txt 文件
# ======================================================================
def list_material_files():
    """功能：列出素材目录里所有 txt 素材文件名
    入参：无（素材目录来自 config.MATERIAL_DIR，本机为
          C:\\Users\\23540\\Desktop\\代码\\答辩\\data\\story_materials）
    返回：文件名列表（已排序），例如 ['小乌龟慢慢上学记.txt', '彩虹色的分享.txt']；
          目录不存在时返回空列表
    使用场景：网页侧边栏"已入库素材清单"展示
    """
    # 把字符串路径转成 Path 对象，方便后面判断和遍历
    material_dir = Path(config.MATERIAL_DIR)
    # 目录不存在就直接返回空列表（不报错，网页才不会崩）
    if not material_dir.exists():
        return []
    file_list = []
    for file_path in material_dir.glob("*.txt"):   # glob 通配符找文件
        file_list.append(file_path.name)           # .name 只取文件名（不带目录）
    return sorted(file_list)                       # 排序后返回，展示更整齐


# ======================================================================
# 函数 3：load_all_documents —— 加载素材（RAG 第 1 步）
# ======================================================================
def load_all_documents():
    """功能：把素材目录下所有 txt 文件加载成 LangChain 的 Document 对象列表
    入参：无
    返回：documents —— 文档列表，每个 Document 对象有 2 个重要属性：
            page_content —— 文本正文（字符串）
            metadata     —— 来源信息（字典，里面 source = 文件路径）
    使用场景：构建向量库的第 1 步
    """
    # 1. 先找出所有 txt 文件
    material_dir = Path(config.MATERIAL_DIR)
    txt_files = list(material_dir.glob("*.txt"))
    if len(txt_files) == 0:
        # 没有素材别硬跑，抛出中文错误让用户知道该干什么
        raise RuntimeError("素材目录为空，请先在网页端上传 txt 儿童故事素材文件")

    # 2. 逐个文件用 TextLoader 加载
    all_documents = []
    for file_path in txt_files:
        # TextLoader 是 LangChain 核心的纯文本加载器，读取文件内容
        loader = TextLoader(str(file_path), encoding="utf-8")
        # load() 返回列表（一个文件对应一个 Document）
        docs = loader.load()
        # extend 逐个追加（对比 append：append 会把整个列表塞成一个元素）
        all_documents.extend(docs)

    # 3. 过滤掉空文件
    valid_documents = []
    for doc in all_documents:
        content = doc.page_content
        if content is not None and content.strip() != "":
            valid_documents.append(doc)
    if len(valid_documents) == 0:
        raise RuntimeError("素材文件内容为空，请检查上传的 txt 是否有正文")

    return valid_documents


# ======================================================================
# 函数 4：split_documents —— 文本切分（RAG 第 2 步）
# ======================================================================
def split_documents(documents):
    """功能：把长文章切成小块（chunk），便于后面向量化和精准检索
    入参：
        documents —— 上一步 load_all_documents() 返回的文档列表
    返回：chunks —— 切分后的小文本块列表，每个元素仍是 Document 对象
    使用场景：构建向量库的第 2 步；CHUNK_SIZE / CHUNK_OVERLAP 是课堂调参重点
    """
    # RecursiveCharacterTextSplitter：递归字符切分器
    # 它会按 separators 列表从"大分隔符"往"小分隔符"逐级尝试，
    # 尽量在语义边界（段落、句号）处切开，而不是硬切
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,        # 每块最大字符数（默认 300）
        chunk_overlap=config.CHUNK_OVERLAP,  # 相邻块重叠字符数（默认 50）
        separators=[
            "\n\n",  # 段落分隔
            "\n",    # 换行
            "。",    # 中文句号
            "！",    # 感叹号
            "？",    # 问号
            "；",    # 分号
            "，",    # 逗号
            " ",     # 空格
            "",      # 字符级切分（兜底）
        ],
    )
    # 执行切分
    chunks = splitter.split_documents(documents)
    return chunks


# ======================================================================
# 函数 5：build_vector_store —— 构建向量库并保存到磁盘（RAG 第 3+4 步）
# ======================================================================
def build_vector_store() -> int:
    """功能：完整执行"加载 -> 切分 -> 向量化 -> 保存到磁盘"四步，构建 FAISS 向量库
    入参：无
    返回：切分出的文本片段数量（整数，用于网页上展示构建结果）
    使用场景：网页侧边栏点击"构建/更新向量知识库"按钮时调用
    """
    # 第 1 步：加载文档
    documents = load_all_documents()
    # 第 2 步：文本切分
    chunks = split_documents(documents)
    # 第 3 步：向量化 + 第 4 步：放进 FAISS 向量库
    global _vector_store                      # 要修改模块级变量，必须声明 global
    _vector_store = FAISS.from_documents(chunks, get_embeddings())
    # 保存到磁盘：以后重启程序不用重新构建，直接加载磁盘上的索引
    # mkdir(parents=True, exist_ok=True)：目录不存在就自动创建（含多级父目录）
    Path(config.FAISS_INDEX_PATH).mkdir(parents=True, exist_ok=True)
    # 【注意】这里必须"切到项目根 + 用相对路径"保存，原因见 _in_project_root 的说明
    with _in_project_root():
        _vector_store.save_local(_faiss_index_rel())
    # 返回片段数量，让网页渲染构建结果
    return len(chunks)


# ======================================================================
# 函数 6：load_vector_store —— 从磁盘懒加载向量库
# ======================================================================
def load_vector_store():
    """功能：从磁盘加载之前构建好的 FAISS 向量库（懒加载，只加载一次）
    入参：无
    返回：vector_store —— FAISS 向量库对象；如果从未构建过则返回 None
    使用场景：检索前调用，保证拿到一个可用的向量库
    """
    global _vector_store
    if _vector_store is None:                 # 内存里还没有，尝试从磁盘加载
        # 判断磁盘有没有保存过的索引文件
        index_file = Path(config.FAISS_INDEX_PATH) / "index.faiss"
        if index_file.exists():
            # FAISS 本地索引是 pickle 序列化文件，加载时要显式授权
            # （allow_dangerous_deserialization=True 的含义：我确认这个索引是我自己构建的可信文件）
            # 【注意】同样要"切到项目根 + 用相对路径"，原因见 _in_project_root 的说明
            with _in_project_root():
                _vector_store = FAISS.load_local(
                    _faiss_index_rel(),
                    get_embeddings(),
                    allow_dangerous_deserialization=True,
                )
    return _vector_store                      # 没构建过就返回 None


# ======================================================================
# 函数 7：search_from_vector_store —— 向量检索（RAG 第 4 步的"检索"）
# ======================================================================
def search_from_vector_store(query: str, top_k: int = None):
    """功能：把问题向量化，在 FAISS 里检索最相似的 top_k 个片段
    入参：
        query  —— 检索问题/关键词（字符串），例如"关于分享的小故事素材"
        top_k  —— 返回几个片段（不传就用 config.RAG_TOP_K）
    返回：hits —— 检索结果列表，每个元素是 (Document, 分数)；
                 FAISS 默认用 L2 距离，分数越小表示越相似
    使用场景：RAG 检索工具（story_material_search）的核心逻辑
    """
    # 先拿到向量库（没有构建过会返回 None）
    vector_store = load_vector_store()
    if vector_store is None:
        return None   # 返回 None 表示"知识库还没构建"

    # 没传 top_k 就用配置里的默认值
    if top_k is None:
        top_k = config.RAG_TOP_K

    # 相似度检索：内部会先把 query 转成向量，再和库里的向量逐个算距离
    hits = vector_store.similarity_search_with_score(query, k=top_k)
    return hits


# ======================================================================
# 函数 8：format_search_result —— 把检索结果格式化成好看的文本
# ======================================================================
def format_search_result(hits):
    """功能：把检索结果列表拼成一段适合塞进提示词的文本
    入参：
        hits —— search_from_vector_store() 返回的检索结果列表
    返回：格式化后的文本字符串（没有结果时返回 None）
    使用场景：检索结果最终要交给大模型阅读，格式清晰模型才用得好
    """
    if not hits:
        return None

    parts = []   # 先收集每一段的文字，最后统一拼接
    for i, (doc, score) in enumerate(hits, 1):
        # 这行用到了 Day1 学的两个语法：
        #   ① 元组解包 (doc, score) —— 一次取出两个值
        #   ② enumerate(hits, 1)    —— 同时拿到序号和元素，序号从 1 开始
        # 从 metadata 里取出源文件名（source 存的是完整路径，basename 只留文件名）
        source = os.path.basename(doc.metadata.get("source", "未知文件"))
        # 拼接第 i 个片段：来源 + 分数 + 正文
        parts.append(
            f"【素材片段{i}】来源文件：{source}（相似度分数：{score:.4f}，越小越相关）\n"
            f"{doc.page_content.strip()}"
        )
    # 片段之间空一行，方便大模型区分
    return "\n\n".join(parts)


# ======================================================================
# 函数 9：retrieve —— 对外统一入口（Agent 工具直接调用这个函数）
# ======================================================================
def retrieve(query: str, top_k: int = None) -> str:
    """功能：RAG 检索的统一入口：检索 + 格式化，一步到位
    入参：
        query —— 检索问题/关键词（字符串）
        top_k —— 返回片段数量（选填，默认取 config.RAG_TOP_K）
    返回：格式化好的检索结果文本（字符串）。
          知识库没构建 / 没匹配时返回"提示文字"而不是报错——
          这样 Agent 拿到提示后还能照常创作，不会中断对话。
    使用场景：agent_service.py 里的 story_material_search 工具调用
    """
    # 情况 1：知识库还没构建过
    vector_store = load_vector_store()
    if vector_store is None:
        return "（知识库为空：尚未上传故事素材并构建向量库，本次创作将不参考素材）"

    # 情况 2：正常检索
    hits = search_from_vector_store(query, top_k)

    # 情况 3：检索了但没有结果
    if not hits:
        return "（知识库中未检索到与该问题相关的素材）"

    # 情况 4：检索成功，格式化后返回
    return format_search_result(hits)


# ======================================================================
# 单独运行本文件时的自测（python rag_service.py）
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("验证函数 1：Embedding 模型（首次下载约 100MB，请耐心等待）")
    print("=" * 60)
    emb = get_embeddings()
    vec = emb.embed_query("勇敢的小兔子")   # 把一句话变成向量
    print(f"向量长度：{len(vec)}")          # bge-small 的向量维度
    print(f"前5个数字：{vec[:5]}")          # 一串数字，就是这句的"语义坐标"

    print()
    print("=" * 60)
    print("验证函数 2：素材文件清单")
    print("=" * 60)
    print(list_material_files())

    print()
    print("=" * 60)
    print("验证函数 3~4：加载 + 切分")
    print("=" * 60)
    docs = load_all_documents()
    print(f"共加载 {len(docs)} 个文档")
    print(f"第一个文档来源：{docs[0].metadata['source']}")
    print(f"正文前50个字：{docs[0].page_content[:50]}")
    chunks = split_documents(docs)
    print(f"切分后共 {len(chunks)} 个片段")
    for i, c in enumerate(chunks[:3], 1):
        print(f"  {i}号片段 {len(c.page_content)}字：{c.page_content[:60]}...")

    print()
    print("=" * 60)
    print("验证函数 5：构建向量库")
    print("=" * 60)
    print(f"构建完成，共 {build_vector_store()} 个片段")

    print()
    print("=" * 60)
    print("验证函数 6：从磁盘加载向量库")
    print("=" * 60)
    vs = load_vector_store()
    print("向量库对象是否可用：", vs is not None)

    print()
    print("=" * 60)
    print("验证函数 7~9：检索三种情况")
    print("=" * 60)
    print("【语义相关·分享】")
    print(retrieve("关于分享的故事"))
    print()
    print("【语义相关·坚持不懈】")
    print(retrieve("坚持不懈"))
    print()
    print("【完全不相关·宇宙飞船】")
    print(retrieve("宇宙飞船"))
