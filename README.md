# 儿童故事创作智能体（实训项目）

用 Python 手写一个"会查资料、会写故事、会自己存档"的智能体网页。
家长/老师输入故事主题、主角、年龄段、教育寓意，智能体自动检索素材 → 创作故事 → 存进数据库。

**技术栈**：Python 3.13 + LangChain 0.3 + DeepSeek + FAISS + MySQL 8.0 + Streamlit

---

## 一、项目结构（按职责分层）

```
答辩/
├── app.py                      ★ 启动入口：streamlit run app.py
├── src/                        源码包
│   ├── config.py               全局配置（读 .env、启动校验）
│   ├── core/                   业务核心层
│   │   ├── agent_service.py    智能体：提示词 + 两个工具 + 决策循环 + 流式输出
│   │   ├── rag_service.py      RAG：素材切分 → 向量化 → FAISS 建库 / 检索
│   │   └── db_util.py          MySQL 封装（pymysql 五步曲）
│   └── ui/                     界面层
│       └── clarify_form.py     需求澄清问卷组件
├── tests/                      分模块自测脚本
│   ├── test_db.py              Day2 数据库层
│   ├── test_rag.py             Day3 RAG 检索
│   ├── test_tools.py           Day4 工具
│   ├── test_agent.py           Day4 智能体端到端
│   └── test_intent.py          意图路由（前 63 条离线，后 30 条测模型兜底）
├── data/                       素材 txt + FAISS 索引（运行时生成）
├── models/                     本地 Embedding 模型
├── sql/init.sql                建库建表脚本
├── requirements.txt / README.md
└── .env（密钥，不提交）/ .env.example
```

调用关系：

```
app.py（网页门面）
   ├─ 调 src.core.agent_service.chat_stream()  ← 智能体（大模型 + 工具 + 决策循环）
   │     ├─ 调 src.core.rag_service            ← RAG 检索（素材变向量库）
   │     └─ 调 src.core.db_util                ← MySQL 存取（存故事 / 查历史）
   ├─ 调 rag_service 建库 / 检索               ← 知识库构建
   ├─ 调 DBUtil 查历史                         ← 会话 / 故事面板
   └─ from src import config                   ← 全部配置（读 .env）
```

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `src/config.py` | 读 `.env`、集中管理配置、启动校验 | 拦截 `deepseek-reasoner`；把相对路径统一解析成基于项目根的绝对路径 |
| `src/core/db_util.py` | MySQL 封装（pymysql 五步曲） | 参数化查询防 SQL 注入 |
| `src/core/rag_service.py` | RAG 四步流水线 + 9 个函数 | 懒加载 + `global` 声明；内建 faiss 相对路径适配 |
| `src/core/agent_service.py` | 意图路由 + 两个 `@tool` 工具 + Agent 组装 + `chat()` / `chat_stream()` | function-call；`contextvars` 做会话隔离；意图判定走"规则 + 模型兜底"两层 |
| `src/ui/clarify_form.py` | 需求澄清问卷（可点选的选项卡片） | 把模型追问渲染成问卷 |
| `app.py` | Streamlit 网页（会话 / 聊天 / 知识库 / 历史故事） | `st.session_state` |

---

## 二、运行步骤

```bash
# 0. 确认 MySQL 已启动，且已执行建库建表脚本
mysql -uroot -p < sql/init.sql

# 1. 激活虚拟环境（Windows）
.venv\Scripts\activate

# 2. 首次运行需安装依赖（已装可跳过）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 确认 .env 已配置（由 .env.example 复制改名而来）
#    Windows: copy .env.example .env

# 4. 启动网页（在项目根目录执行）
streamlit run app.py
```

浏览器会自动打开 <http://localhost:8501>。

---

## 三、分步自测（每一层单独验证，出问题好定位）

```bash
# 推荐用 -m 形式（在项目根目录执行）
.venv\Scripts\python.exe -m tests.test_db      # Day2 数据库层
.venv\Scripts\python.exe -m tests.test_rag     # Day3 RAG 检索
.venv\Scripts\python.exe -m tests.test_tools   # Day4 工具（注意用 .invoke({...})）
.venv\Scripts\python.exe -m tests.test_agent   # Day4 智能体端到端
.venv\Scripts\python.exe -m tests.test_intent  # 意图路由（前 63 条离线必过；后 30 条需联网，断网自动跳过）

# 也可以直接按路径运行，脚本会自动把项目根加入搜索路径
.venv\Scripts\python.exe tests\test_rag.py
```

---

## 四、本机环境的三处适配（重要，答辩可能被问）

这份代码在你机器上做了 3 处**必要适配**，都写进了注释，原因如下：

### 1. Embedding 模型改成读本地目录

`.env` 里 `EMBEDDING_MODEL` 指向项目内的 `models/bge-small-zh-v1.5`。

**原因**：huggingface_hub 在 Windows 上创建缓存符号链接会失败，下载后 snapshot 里是 0 字节空文件，
模型加载会报 `JSONDecodeError: Expecting value: line 1 column 1`。所以改用 curl 把模型直接下到项目内、
按本地路径加载。换机器时把这一行改回 `BAAI/bge-small-zh-v1.5` 即可。

### 2. FAISS 索引只能走相对路径 → 代码里已自动适配

`.env` 里 `FAISS_INDEX_PATH=data/faiss_index`（按相对路径写即可）。

**原因**：faiss 的 C++ 底层在 Windows 上打不开**带盘符的绝对路径**
（报 `could not open C:\...\index.faiss for writing: No such file or directory`），
只接受相对路径。本项目路径本身又含中文（`代码\答辩`），早年容易被误判成"中文路径问题"——实测纯英文目录的绝对路径同样失败，真正的分界线是"绝对路径 vs 相对路径"。

**重构后已经内建解决，不需要手工规避**：

- `src/config.py` 把 `.env` 里的相对路径统一补成**绝对路径**（`FAISS_INDEX_PATH`），
  Python 侧的文件读写、目录判断都用它，不再依赖"从哪个目录启动"；
- `src/core/rag_service.py` 只在**真正交给 faiss 读写索引**的那两处（`save_local` / `load_local`），
  用 `_in_project_root()` 临时把工作目录切到项目根、再用 `_faiss_index_rel()` 传相对路径，
  用完立刻切回原目录。

**结论：现在从任何目录启动都可以**（`streamlit run app.py`、或 IDE 里直接点运行都行），
不再有"必须在项目根目录启动"的限制。

### 3. Agent 用 `create_tool_calling_agent`，不是 `create_react_agent`

**原因**：langchain 0.3 的 `create_react_agent` 是**文本式 ReAct**，靠
`ReActSingleInputOutputParser` 解析 `Action:` / `Action Input:` 文本，
**只支持单参数工具**——遇到 `story_db_tool` 这种 7 参数工具，会把整串 JSON
当成第一个参数传进去，报"操作类型错误"。

改用 `create_tool_calling_agent`（原生 function-call）后：
- 模型的工具调用参数是结构化的，多参数工具正常工作；
- 这也才真正实现了"function-call / `bind_tools`"这个知识点——
  文本式 ReAct 其实**并不会**调用 `bind_tools`。

ReAct 的"思考 → 行动 → 观察"循环依然成立，只是"行动"从写文本变成了原生函数调用。

---

## 五、意图路由：为什么是"规则 + 模型兜底"两层

`classify_intent()` 决定**这一轮要不要弹需求澄清问卷**，只有判成 `vague` 才弹。
它判错时不会报任何错 —— 只是问卷悄悄不弹，看起来像"点选功能坏了"。所以这块单独说明。

**第一层 · 规则法（默认路径，零成本）**
把句子里的意愿词、量词、故事名词、语气词全部剥掉，剥完什么都不剩 → 模糊需求。
毫秒级、结果可复现、断网也能测。

**规则法的天花板**
它按字面匹配，而人的说法是无穷的。实测 **54 条词表外的口语说法只判对 35 条（64.8%）**
—— "来点哄睡的""想给孩子听点东西""给我叨咕一个吧"这类说法不带任何词表里的词，直接漏掉。

**第二层 · 模型兜底（只在没把握时出手）**
与其无限补词表，不如让规则**只做有把握的部分**：

| 规则判成 | 处理 | 理由 |
| --- | --- | --- |
| `chitchat` / `vague` | 直接采信，**不调模型** | 靠精确词表命中，实测很准 |
| `create`，且命中"主题/主角/年龄/篇幅"等真要素 | 直接采信，**不调模型** | 要素明确，不必复核 |
| `create`，但只沾到"故事/童话/睡前"这类泛词 | 交模型复核 | "睡前来一段"就是靠"睡前"两个字混进 create 的 |
| `other` | 交模型复核 | 本来就是"所有词表都没命中"的不确定档 |

**几个关键设计（答辩可能被问）**

- 主流输入（"你好""写个关于分享的故事"）走规则直接出结果，**零延迟、零费用**；
  只有边缘说法才多花一次约 1 秒、约 50 token 的调用。
- 兜底**永远不抛异常**：超时、欠费、密钥失效一律退回规则结果 ——
  宁可退化成"原来的规则法"，也不能让用户点一下发送就报错。
- 连错 2 次**自动熔断 60 秒**，期间全部走规则法。否则网络一抖，每次输入都要白等 6 秒超时。
- `.env` 里 `INTENT_FALLBACK=false` 可整体关掉第二层（要演示"纯离线也能跑"时用）。
- `chat_stream()` 里这一步是用 `asyncio.to_thread` 调用的 —— 它是 async 函数，
  在里面同步等模型会把事件循环卡住，表现就是"流式输出卡顿、页面不刷新"。

**实测效果（两批留出集，共 54 条词表外说法）**

| 测试集 | 纯规则 | 规则 + 兜底 |
| --- | --- | --- |
| 已固化用例 63 条 | 63/63 | 63/63（兜底一次都没触发） |
| 词表外新说法 54 条 | 35/54 = 64.8% | **54/54** |

另有一项硬指标：**"明确需求被拦成问卷" = 0 条**。
把该创作的需求反问回去，比漏弹问卷更伤体验，所以单列出来盯。

回归用例在 `tests/test_intent.py`：前 63 条离线必过，后 30 条验证兜底能救回（断网自动跳过）。

---

## 六、演示流程（建议 5 分钟版）

1. 上传素材 → 点「🔨 构建/更新向量知识库」→ 看到"共生成 9 个文本片段"；
2. 输入：`创作一个关于勇敢的小兔子的故事，适合3-6岁，教育孩子不要害怕黑暗`；
3. **展开「🔍 Agent 内部执行日志」** ← 重点展示，每步的工具名、参数、返回；
4. 看侧边栏「📖 历史故事」里刚生成的故事（Agent 自己存进去的）；
5. 继续输入 `把主角改成小刺猬` 验证多轮记忆；
6. 点「➕ 新建会话」再下拉切回旧会话，验证历史从 MySQL 恢复。

---

## 七、常见问题速查

| 现象 | 原因 / 解决 |
| --- | --- |
| `MySQL 数据库连接失败` | 检查 MySQL 服务是否启动；`.env` 里密码是否正确；`init.sql` 是否执行 |
| `缺少必需的环境变量【DEEPSEEK_API_KEY】` | `.env` 没建或没填密钥 |
| `知识库为空：尚未上传故事素材` | 素材目录没文件，或没点"构建向量知识库" |
| 模糊需求不弹问卷（点选功能"像坏了"） | 意图路由判错。先看 `tests/test_intent.py` 能否复现；开兜底（`INTENT_FALLBACK=true`）可救回大部分口语说法；确认是漏词后补词表 + 加用例 |
| 每条输入都慢约 1 秒 | 兜底在频繁触发。看日志里"意图兜底修正/确认"的记录；正常主流输入不该触发。可临时 `INTENT_FALLBACK=false` |
| 日志出现"意图兜底不可用…将熔断" | 网络不通/欠费。系统会自动熔断 60 秒并退回规则法，不影响使用 |
| `could not open ...index.faiss for writing` | faiss 在 Windows 上不接受绝对路径。本项目已在 `rag_service` 里用 `_in_project_root()` + `_faiss_index_rel()` 自动适配；若自己改写索引读写逻辑，记得传相对路径 |
| `Invalid Format: Missing 'Action:'` | 用了文本式 `create_react_agent`；改用 `create_tool_calling_agent` |
| `操作类型错误：{...}` | 同上：文本式 ReAct 无法展开多参数工具 |
| 工具测试报 `object is not callable` | `@tool` 装饰后是工具对象，要用 `.invoke({...})` 调用 |
| `JSONDecodeError: Expecting value: line 1 column 1` | Embedding 模型缓存损坏；删除 `~/.cache/huggingface/hub/models--BAAI--*` 重下，或直接用本地模型目录 |

---

## 八、安全约定

- `.env` 含真实密钥与数据库密码，**已被 `.gitignore` 屏蔽，永远不要提交或外发**；
- 模型名称必须 `deepseek-chat`。`deepseek-reasoner`(R1) 不支持 function-call，
  `config.py` 会在启动时直接拦截报错。
