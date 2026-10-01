"""
======================================================================
config.py —— 全局配置文件（新手入门第 1 课就要读懂的文件）
======================================================================

【这个文件是干什么的？】
把 .env 文件里的配置读出来，变成一个个 Python 全局变量。
其他文件（src/core 下的 db_util / rag_service / agent_service，
以及根目录的启动入口 app.py）
只需要写一句 "from src import config"，然后用 config.DEEPSEEK_API_KEY
这样的方式取配置，非常方便。

【为什么要单独写这个文件？】
1. 密钥安全：API 密钥、数据库密码绝对不允许直接写在业务代码里，
   否则代码发给别人/上传 GitHub 时密钥就泄露了（真实发生过密钥被盗刷的事故）；
2. 集中管理：所有"可以调的数字"（超时时间、切块大小、检索条数）
   集中在一个地方，课堂调参实验只需要改这一个文件（或 .env）；
3. 启动即校验：如果忘了配 .env，程序一启动就报出清晰的中文提示，
   而不是跑到一半才莫名其妙地报错。

【修改配置后怎么办？】
config.py 在程序启动（import）时只执行一次，
所以改完 .env 必须重启 Streamlit（Ctrl+C 停掉，重新运行命令）。
"""
import os                      # Python 内置模块：用来读取环境变量 os.getenv()
from pathlib import Path       # Python 内置模块：用来拼文件路径，比字符串拼接更安全、跨平台

from dotenv import load_dotenv # python-dotenv 库：把 .env 文件内容加载成环境变量

# ======================================================================
# 第 1 步：定位项目根目录
# ======================================================================
# __file__   ：Python 自带的魔法变量，代表"本文件自己的路径"
# .resolve() ：把路径转成绝对路径（比如 C:\Users\23540\Desktop\代码\答辩\src\config.py）
# .parent    ：取路径的上一级目录（src/）
# .parent.parent：再退一级，才是项目根目录——因为本文件在 src/ 子目录里
BASE_DIR = Path(__file__).resolve().parent.parent

# ======================================================================
# 第 2 步：加载 .env 文件
# ======================================================================
# 项目根目录下必须有一个 .env 文件（由 .env.example 复制改名而来）
# load_dotenv 执行之后，.env 里每一行 "KEY=VALUE" 都会变成环境变量，
# 之后就能用 os.getenv("KEY") 把它们读出来。
# 如果 .env 不存在，load_dotenv 不会报错（静默跳过），
# 但后面读取"必需配置"时会报出"缺少配置"的清晰错误。
load_dotenv(BASE_DIR / ".env")


# ======================================================================
# 第 3 步：写一个读取环境变量的小工具函数
# ======================================================================
def read_env(key: str, default: str = "", required: bool = False) -> str:
    """功能：读取一个环境变量，可以设置默认值、可以设置"必须存在"
    入参：
        key      —— 环境变量的名字（字符串），例如 "DEEPSEEK_API_KEY"
        default  —— 默认值（字符串）。当 .env 里没写这个变量时使用它，默认空串
        required —— 是否必须存在（布尔值）。True 表示这个变量没配就直接报错
    返回：读到的配置值（字符串）
    使用场景：第 4~7 步读取每个配置项时统一调用，避免重复写判断代码
    """
    # os.getenv 读环境变量；没读到就用 default 顶替
    value = os.getenv(key, default)
    # 如果这个变量是"必须存在"的，但值是空串/None，就直接报错并给出修复提示
    if required and (value is None or str(value).strip() == ""):
        raise RuntimeError(
            f"缺少必需的环境变量【{key}】！\n"
            f"解决方法：复制 .env.example 为 .env，然后填入你自己的配置（详见 README.md）。"
        )
    return value


def resolve_path(value: str, default_rel: str) -> str:
    """功能：把配置里的目录统一解析成"绝对路径"
    入参：
        value       —— .env 里读到的路径（可能是空串 / 相对路径 / 绝对路径）
        default_rel —— 默认的相对路径（相对项目根目录）
    返回：绝对路径字符串
    使用场景：读取"素材目录""向量库目录"这类路径型配置时统一调用。
    为什么需要这一步：
        .env 里如果写 "data/story_materials" 这种相对路径，
        它的真实含义取决于"从哪个目录启动程序"——换个目录启动就找不到文件了。
        统一在这里拼上 BASE_DIR，语义就固定成"相对项目根目录"，稳。
    """
    p = Path(value) if str(value).strip() else Path(default_rel)
    if not p.is_absolute():
        p = BASE_DIR / p        # 相对路径 → 相对项目根目录展开
    return str(p)


# ======================================================================
# 第 4 步：读取 DeepSeek 大模型配置
# ======================================================================
# API 密钥：到 https://platform.deepseek.com 注册后自己申请，严禁写死在代码里
DEEPSEEK_API_KEY = read_env("DEEPSEEK_API_KEY", required=True)
# 接口地址：DeepSeek 官方地址，一般不需要修改
DEEPSEEK_BASE_URL = read_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# 模型名称：必须使用 deepseek-chat！
DEEPSEEK_MODEL = read_env("DEEPSEEK_MODEL", "deepseek-chat")

# ---- 超级重要的踩坑拦截 ----
# deepseek-reasoner（R1 深度思考模型）不支持 function-call 工具调用，
# 用它 Agent 会完全无法调用工具（本课程第 4 天会深入讲解原理）。
# 这里在程序启动时就拦截，避免学生带着错误配置跑一整天。
if DEEPSEEK_MODEL == "deepseek-reasoner":
    raise RuntimeError(
        "禁止使用 deepseek-reasoner（R1）模型！它不支持 function-call 工具调用，"
        "会导致 Agent 无法调用工具。请把 .env 里的 DEEPSEEK_MODEL 改成 deepseek-chat。"
    )

# 单次请求超时秒数：校园网慢的时候可以调大（例如 120）
DEEPSEEK_TIMEOUT = int(read_env("DEEPSEEK_TIMEOUT", "60"))
# 请求失败自动重试次数：网络抖动时自动重试，避免一次失败整个程序崩溃
DEEPSEEK_MAX_RETRIES = int(read_env("DEEPSEEK_MAX_RETRIES", "2"))
# 单次回复最大 token 数：故事比较长，默认 4000 比较稳妥
DEEPSEEK_MAX_TOKENS = int(read_env("DEEPSEEK_MAX_TOKENS", "4000"))
# 创作温度（取值 0~2）：温度越高越有创意、越不容易"套路化"。
# 儿童故事创作调到 0.9，是为了让每篇故事的角色、场景、情节更不一样；
# 【课堂调参实验】把它改成 0.1 再连续创作两篇，就能直观看到"两篇故事高度雷同"。
DEEPSEEK_TEMPERATURE = float(read_env("DEEPSEEK_TEMPERATURE", "0.9"))

# ======================================================================
# 第 5 步：读取 MySQL 数据库配置
# ======================================================================
# 数据库地址：本机就是 127.0.0.1（localhost）
MYSQL_HOST = read_env("MYSQL_HOST", "127.0.0.1")
# 数据库端口：MySQL 默认端口 3306
MYSQL_PORT = int(read_env("MYSQL_PORT", "3306"))
# 数据库账号：默认 root（你自己装 MySQL 时设置的那个账号）
MYSQL_USER = read_env("MYSQL_USER", "root")
# 数据库密码：从 .env 读取，绝不写死在代码里！
MYSQL_PASSWORD = read_env("MYSQL_PASSWORD", "")
# 数据库名：sql/init.sql 里创建的那个库名
MYSQL_DB = read_env("MYSQL_DB", "children_story_db")

# ======================================================================
# 第 6 步：读取 RAG 知识库配置
# ======================================================================
# 中文 Embedding 模型：把中文句子变成向量（一串数字）
# 首次使用会自动从 HuggingFace 下载（约 100MB），
# 网络慢时在终端设置镜像再启动：HF_ENDPOINT=https://hf-mirror.com
EMBEDDING_MODEL = read_env("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
# 素材存放目录：网页上传的 txt 会保存到这里
# （.env 里写相对路径如 data/story_materials 即可，这里会自动补成基于项目根目录的绝对路径）
MATERIAL_DIR = resolve_path(read_env("MATERIAL_DIR", ""), "data/story_materials")
# FAISS 向量索引保存目录：构建好的向量库存在这里，重启程序不用重新构建
FAISS_INDEX_PATH = resolve_path(read_env("FAISS_INDEX_PATH", ""), "data/faiss_index")
# 文本切分块大小（字符数）：课堂调参实验重点！切太大检索不准，切太小语义破碎
CHUNK_SIZE = int(read_env("CHUNK_SIZE", "300"))
# 相邻文本块重叠的字符数：防止一句话被从中间切断
CHUNK_OVERLAP = int(read_env("CHUNK_OVERLAP", "50"))
# 每次检索返回的最相关片段数量
RAG_TOP_K = int(read_env("RAG_TOP_K", "3"))

# ======================================================================
# 第 7 步：读取 Agent 配置
# ======================================================================
# 工具调用最大轮数：防止 Agent 陷入"死循环"一直调用工具
AGENT_MAX_ITERATIONS = int(read_env("AGENT_MAX_ITERATIONS", "10"))
# 注入提示词的历史对话轮数：多轮对话时带多少"记忆"
MAX_HISTORY_TURNS = int(read_env("MAX_HISTORY_TURNS", "6"))

# ======================================================================
# 第 8 步：读取「意图路由」配置（规则 + 模型兜底）
# ======================================================================
# 【背景】意图路由（classify_intent）决定"这一轮要不要弹需求澄清问卷"。
#   默认走规则法：剥词表 → 零成本、毫秒级、结果可复现、离线能测。
#   但规则法遇到词表没收录的口语说法会漏判，而且**漏了不报错**，
#   只是问卷悄悄不弹（实测：词表外的 26 条说法里错了 11 条，57.7%）。
# 【兜底】规则判不准时（判成"其它"，或只靠"故事"这类泛词判成"明确需求"），
#   调用一次极轻量的大模型复核（只输出一个类别词，约 50 token）。
#   高置信的判断（纯寒暄、剥完为空、命中主题/主角/年龄等强要素）不调模型，
#   所以日常主流输入零延迟、零费用。
INTENT_FALLBACK = read_env("INTENT_FALLBACK", "true").lower() in ("1", "true", "yes", "on")
# 兜底调用的超时（秒）：刻意给得短。正常响应约 0.5~1.5 秒；网络不通时宁可
# 快速退回规则结果，也不能让"判个意图"把整轮对话卡住 —— 降级要快、要无感。
# （连错 2 次后会自动熔断 60 秒，期间全部走规则法，见 agent_service._llm_intent）
INTENT_FALLBACK_TIMEOUT = int(read_env("INTENT_FALLBACK_TIMEOUT", "6"))
