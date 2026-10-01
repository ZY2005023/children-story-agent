"""
======================================================================
app.py —— Streamlit 网页主程序（项目启动入口）
======================================================================

【这个文件是干什么的？】
整个项目的"门面"：学生打开浏览器，看到的就是这个网页。
它把 src/ 下的配置与业务模块（config 与 core 里的 agent_service、
rag_service、db_util）串起来，提供四大功能：
1. 会话管理：新建会话、切换历史会话
2. 聊天主界面：输入框发消息、展示 AI 回复、展示 Agent 工具调用日志
3. RAG 知识库区：上传 txt 素材、一键构建向量库
4. 历史故事面板：从 MySQL 读出所有已保存的故事，点开查看全文

【Streamlit 最重要的一个概念：执行模型（必考）】
普通程序：启动后一直运行，等用户操作。
Streamlit：用户每操作一次（点按钮、发消息），整个脚本从头到尾重跑一遍！
所以跨操作要保留的数据必须放进 st.session_state（类似"白板"，
Streamlit 帮我们把白板上的内容一直保存着）。

【运行方式】
在项目根目录打开终端，执行：streamlit run app.py
浏览器会自动打开 http://localhost:8501
"""
import asyncio                       # 异步：驱动智能体的流式输出（"打字机"效果）
import re                            # 正则：从回答里提取《故事标题》
import time                          # 计时：给流式刷新做节流，避免刷太勤把页面卡住
import uuid                          # 生成随机ID，用来做 session_id（会话编号）
from pathlib import Path             # 拼文件路径
import sys                           # 路径处理：把项目根目录加入模块搜索路径


# 【为什么要这几行】本项目采用 src/ 包结构（所有源码都放在 src/ 目录下）。
# 无论用哪种方式启动（命令行 streamlit run app.py、还是 IDE 里直接点运行），
# 都先把"项目根目录"加进 sys.path，
# 这样 from src import config / from src.core import xxx 一定能导入成功。
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st               # 网页框架

from src import config               # 导入即完成 .env 读取与配置校验（密钥检查在这里发生）
from src.ui import clarify_form      # 需求澄清问卷（可点选的选项卡片）
from src.core import rag_service     # RAG 知识库服务
from src.core.agent_service import chat_stream, format_history_text  # 智能体服务（流式入口）
from src.core.db_util import DBUtil  # 数据库工具类

# ======================================================================
# 第 1 步：页面基本设置
# ======================================================================
st.set_page_config(
    page_title="儿童故事创作智能体",   # 浏览器标签页上的标题
    page_icon="📖",                    # 标签页图标
    layout="wide",                     # 宽屏布局（左侧侧边栏 + 右侧主区域）
)

# ======================================================================
# 第 2 步：初始化会话状态 st.session_state
# ======================================================================
# 回忆 Streamlit 执行模型：每次交互脚本都重跑，普通变量会被"清零"。
# st.session_state 里的数据由 Streamlit 帮我们保存，重跑不会丢。
# 下面两句的意思是：如果"白板"上还没有这个变量，就写入初始值；有了就跳过。

if "session_id" not in st.session_state:
    # 生成一个 12 位随机ID作为新会话编号
    # （uuid4().hex 返回 32 位字符串，取前 12 位方便课堂展示）
    st.session_state.session_id = uuid.uuid4().hex[:12]

if "messages" not in st.session_state:
    # messages 存放当前会话的界面消息，每条消息是一个字典：
    # {"role": "user" 或 "assistant", "content": "消息文本"}
    st.session_state.messages = []


# ======================================================================
# 第 3 步：两个"安全查询"小工具函数（数据库异常时降级，不让网页崩溃）
# ======================================================================
def safe_get_sessions():
    """功能：查询历史会话列表（数据库异常时降级返回空列表）
    入参：无
    返回：会话列表（数据库正常时）；[]（数据库异常时）
    使用场景：侧边栏"切换历史会话"下拉框的数据来源
    """
    try:
        return DBUtil.get_all_sessions()
    except Exception as error:
        # 数据库挂了也不崩溃，只在侧边栏给个黄色警告
        st.sidebar.warning(f"⚠️ 加载历史会话失败：{error}")
        return []


def safe_get_history(session_id):
    """功能：查询某个会话的对话记录（数据库异常时降级返回空列表）
    入参：
        session_id —— 会话ID
    返回：对话记录列表（数据库正常时）；[]（数据库异常时）
    使用场景：① 切换会话时加载历史消息 ② 拼多轮对话上下文
    """
    try:
        return DBUtil.get_chat_history(session_id)
    except Exception as error:
        st.sidebar.warning(f"⚠️ 加载会话记录失败：{error}")
        return []


def called_story_save(steps):
    """功能：判断本轮 Agent 有没有调用"保存故事"这个动作
    入参：
        steps —— result["intermediate_steps"]，元素是 (action, observation) 元组
    返回：True —— 本轮调用过 story_db_tool 且 action="save"
          False —— 没调用过
    使用场景：兜底展示前先确认"这一轮确实刚生成并保存了故事"，
              否则会把上一轮的故事误补到这一轮的回复里
    """
    for action, _observation in steps:
        # action.tool 是工具名；action.tool_input 是参数字典，含 action="save"
        if getattr(action, "tool", "") == "story_db_tool" and "save" in str(action.tool_input):
            return True
    return False


def claims_saved(text):
    """功能：检查回答里有没有"声称已存档"的字样（模型幻觉核查）
    入参：
        text —— 最终回答文本
    返回：True —— 回答里提到了已保存/已存档；False —— 没提
    使用场景：配合"本轮是否真的调用了保存工具"做一致性核查。
              实测发现模型有时跳过保存工具，却在回答末尾写"这个故事已经帮您存档啦"，
              用户去左侧「历史故事」里一查什么都没有——属于系统在撒谎。
    注意：关键词要写宽一点。"已经帮您存档啦"里并没有"已存档"三个连续的字，
          只有"存档"——实测就是这里漏过一次，所以宁可多触发（多存一份无害），
          也不能漏触发（漏了就是页面上写着已存储、库里查不到）。
    """
    keywords = ["已保存", "已存档", "已存入", "保存到数据库", "存入故事库",
                "成功保存", "存档", "存好"]
    return any(word in text for word in keywords)


def guess_story_from_answer(answer, user_input):
    """功能：从最终回答里粗略解析出"故事标题"和"故事正文"（自动补存专用）
    入参：
        answer     —— 最终回答全文
        user_input —— 用户本轮输入（实在找不到标题时用它兜底）
    返回：(标题, 正文) 二元组
    使用场景：模型忘记调用保存工具、但回答里已经是完整故事时，用它补存进故事库
    说明：这里只做粗解析，够用就行——目标是"让故事在历史故事面板里找得到"，
          不做精确定位，避免过度设计。
    """
    title = ""
    body_lines = []
    for line in answer.splitlines():
        stripped = line.strip()
        # 优先认 markdown 一级标题（"# xxx"），但排除"一、二、三"这类结构小标题
        if not title and stripped.startswith("# "):
            candidate = stripped[2:].strip()
            if not candidate.startswith(("一、", "二、", "三、", "1.", "2.", "3.")):
                title = candidate
                continue      # 标题已经单独存字段了，正文里不再重复放一遍
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not title:
        # 退一步：全文里找《书名号》——模型很喜欢在正文里写《故事名》
        matched = re.search(r"《([^》]{2,30})》", answer)
        if matched:
            title = matched.group(1).strip()
    if not title:
        # 再找不到就用用户输入前 20 字，至少能在面板里认出来是哪篇
        title = user_input.strip()[:20] or "未命名故事"
    if not body:
        body = answer
    return title, body


# ======================================================================
# 第 4 步：页面标题区
# ======================================================================
st.title("📖 儿童故事创作智能体")
st.caption("LangChain + DeepSeek + FAISS + MySQL ｜ 实训教学演示：多轮对话 · RAG检索 · 工具调用")
st.caption("示例提问：创作一个关于勇敢的小兔子的故事，适合3-6岁，教育孩子不要害怕黑暗")
st.caption("💡 需求说得模糊也没关系（比如只说「写个故事」），会弹出一张小问卷让你直接**点选**"
           "主角 / 道理 / 年龄段 / 篇幅，选完即可开写，不用手敲编号；"
           "每篇故事都会随机换一套新设定，尽量避免千篇一律。")


# ======================================================================
# 第 5 步：侧边栏（with st.sidebar 代码块里的内容都会显示在左边竖条区域）
# 侧边栏从上到下分三个区：会话管理 / RAG知识库 / 历史故事
# ======================================================================
with st.sidebar:

    # ---------------- 5.1 会话管理区 ----------------
    st.header("🗂️ 会话管理")

    # "新建会话"按钮：st.button 点击后返回 True，代码就执行 if 里面的内容
    if st.button("➕ 新建会话", use_container_width=True):
        # 换一个全新 session_id（相当于"开一个新聊天窗口"）
        st.session_state.session_id = uuid.uuid4().hex[:12]
        # 清空界面消息列表
        st.session_state.messages = []
        # 【关键·踩坑修复】把下拉框"记着的上一次选择"清掉。
        # 【症状】先切换过历史会话，再点"新建会话"会毫无反应（ID 还是旧的）。
        # 【原因】st.selectbox 只要给了 key，就会把用户的选择一直存在
        #         st.session_state["session_selector"] 里。点"新建会话"触发
        #         重跑时，下面那段"选中了就切会话"的逻辑又会被这个旧选择触发，
        #         把 session_id 当场改回旧会话 —— 一进一出，看着就像没反应。
        # 【为什么写在这里是安全的】Streamlit 只禁止修改"本轮脚本中已经出现过"
        #         的控件状态；这个按钮在代码里排在下拉框前面，此刻下拉框还没出现，
        #         所以可以放心清空。
        st.session_state.pop("session_selector", None)
        # st.rerun()：重新执行整个脚本，让界面立刻刷新成新会话的样子
        st.rerun()

    # 显示当前会话ID（st.caption 是小号说明文字）
    st.caption(f"当前会话ID：`{st.session_state.session_id}`")

    # ---- 历史会话下拉框：切换会话 ----
    sessions = safe_get_sessions()   # 从数据库查所有历史会话
    if sessions:
        # 【设计要点】下拉框的"选项值"直接用 session_id（它是稳定不变的），
        # 再用 format_func 把它"显示"成"会话ID前8位 + 消息数 + 最近活跃时间"。
        # 【为什么不直接拿拼好的那串文字当选项】因为文字里有"消息数/时间"，
        #   这些是会变的：切到某会话后发一条消息，消息数就从"1条"变"2条"，
        #   下拉框里存的还是旧文字，新旧对不上 —— 实测表现为"选中状态被悄悄
        #   清空"（下拉框自己弹回未选中）。另外旧写法还要用
        #   `labels.index(文字)` 按文字反查是哪条会话，文字一变就查不到。
        #   用 session_id 当值，显示文字怎么变都不影响"选中了谁"。
        session_ids = [s["session_id"] for s in sessions]
        session_labels = {
            s["session_id"]: f"{s['session_id'][:8]}｜{s['msg_count']}条消息｜{s['last_time']}"
            for s in sessions
        }
        # st.selectbox 是下拉框；index=None 表示默认不选中；placeholder 是提示文字
        chosen = st.selectbox(
            "切换历史会话", session_ids, index=None,
            format_func=lambda sid: session_labels.get(sid, sid),
            placeholder="选择要切换的会话……", key="session_selector",
        )
        if chosen and chosen != st.session_state.session_id:
            # 切换到历史会话：设置新ID，并从数据库加载该会话的全部消息
            st.session_state.session_id = chosen
            st.session_state.messages = []
            for row in safe_get_history(chosen):
                # 数据库一行记录 = 一轮问答，拆成两条界面消息
                st.session_state.messages.append({"role": "user", "content": row["user_query"]})
                st.session_state.messages.append({"role": "assistant", "content": row["ai_answer"]})
            st.rerun()   # 刷新界面，让历史消息显示出来
    else:
        st.caption("暂无历史会话")

    st.divider()   # 画一条分隔线

    # ---------------- 5.2 RAG 知识库区 ----------------
    st.header("📚 故事素材知识库（RAG）")
    st.caption("上传 txt 儿童故事素材文件，一键构建 FAISS 向量知识库")

    # st.file_uploader 是文件上传控件；type 限制只能选 txt；
    # accept_multiple_files=True 允许一次选多个文件
    uploaded_files = st.file_uploader(
        "上传 txt 素材（可多选）", type=["txt"], accept_multiple_files=True,
        help="上传后需点击下方按钮构建/更新向量知识库，Agent 才会检索到这些素材",
    )
    if uploaded_files:
        # 把上传的文件逐个保存到素材目录（同名文件会被覆盖）
        material_dir = Path(config.MATERIAL_DIR)
        material_dir.mkdir(parents=True, exist_ok=True)   # 目录不存在就先创建
        saved = []
        for f in uploaded_files:
            # f.getvalue() 拿到文件的字节内容，write_bytes 写入磁盘
            (material_dir / f.name).write_bytes(f.getvalue())
            saved.append(f.name)
        st.success(f"已接收素材文件：{'、'.join(saved)}")

    # "构建/更新向量知识库"按钮：点击后走完 RAG 四步流程
    if st.button("🔨 构建/更新向量知识库", use_container_width=True):
        # st.spinner 是"转圈等待"提示，构建期间一直显示
        with st.spinner("正在加载文档→文本切分→Embedding向量化→写入FAISS……首次运行需下载Embedding模型，请耐心等待"):
            try:
                chunk_count = rag_service.build_vector_store()   # 核心一步
                st.success(f"✅ 知识库构建完成，共生成 {chunk_count} 个文本片段")
            except Exception as error:
                st.error(f"❌ 知识库构建失败：{error}")

    # 展示已入库的素材文件清单
    files = rag_service.list_material_files()
    if files:
        st.caption(f"已入库素材（{len(files)} 个）：" + "、".join(files))

    st.divider()

    # ---------------- 5.3 历史故事面板 ----------------
    st.header("📖 历史故事")
    st.caption("读取 MySQL children_story 表，点击标题展开查看完整故事")
    try:
        stories = DBUtil.get_all_stories()   # 从数据库读全部故事
    except Exception as error:
        st.warning(f"⚠️ 加载历史故事失败：{error}")
        stories = []   # 数据库异常时置空，保证页面还能用
    if not stories:
        st.caption("暂无已保存的故事")
    # 循环展示每篇故事：st.expander 是"点击展开"折叠面板
    for s in stories:
        with st.expander(f"《{s['story_title']}》｜适合{s['age_group']}"):
            st.caption(f"主角：{s['main_role']}｜会话：{s['session_id'][:8]}｜保存时间：{s['create_time']}")
            st.markdown(s["story_content"])          # 故事正文
            st.info(f"💡 教育寓意：{s['moral']}")     # st.info 是蓝色提示框


# ======================================================================
# 第 6 步：主区域 —— 聊天界面
# ======================================================================
# ---- 6.1 先把当前会话的历史消息渲染出来 ----
# st.chat_message(角色) 创建一条"气泡"，角色为 user 显示在右侧，
# 角色为 assistant 显示在左侧（Streamlit 自动排版）
#
# 【特殊处理：需求澄清问卷】如果某条回复带 clarify 标记（说明它是一条
# "我还不知道你要什么故事、先问你几个小问题"的回复），且它正好是最后一条，
# 就把它渲染成可点选的问卷，而不是那段"请回复编号 1A 2B 3B"的文字清单。
# 历史中间位置的旧问卷仍按普通文字显示（那是聊天记录，不需要再交互）。
last_index = len(st.session_state.messages) - 1
clarify_answer = None       # 用户在问卷里点完「开始创作」后，这里会拿到拼好的需求句
clarify_uid = ""            # 问卷的状态前缀（隔离不同问卷的白板，避免互相串台）

for index, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg.get("clarify"):
            if index == last_index:
                # 最后一条 = 正在等你回答：渲染成可点选的问卷
                # uid 里带上会话ID和消息序号：换会话、换位置都不会串状态
                clarify_uid = f"cf{st.session_state.session_id[:6]}_{index}"
                clarify_answer = clarify_form.render_form(clarify_uid)
            else:
                # 已经不是最后一条了（比如你没点选项、直接打字说了需求）：
                # 这条就退化成一句历史记录，不再铺整份清单占地方
                st.markdown("（我当时还不知道你想要什么故事，问了你几个小问题～）")
        else:
            st.markdown(msg["content"])   # markdown 渲染文本，支持标题/列表

# 用户答完问卷点了「开始创作」（或「全部跳过」）——把这条问卷消息收掉，
# 换成"用户解答 + 新故事"，并把拼好的需求句当作本轮用户输入继续往下走。
# 注意这里必须 st.rerun()：让界面先刷新成"问卷已消失"的样子，
# 否则会出现"问卷还在、故事也在"的重叠。
if clarify_answer:
    st.session_state.messages.pop(last_index)      # 收掉问卷那条消息
    clarify_form.reset_form(clarify_uid)           # 清掉问卷的答题白板
    st.session_state["_pending_input"] = clarify_answer   # 暂存，紧接着当作用户输入消费
    st.rerun()

# ---- 6.2 底部输入框 ----
# st.chat_input 固定渲染在页面底部；用户回车后返回输入的文字，没有输入时返回 None
user_input = st.chat_input("在这里输入你的需求：故事主题、主角名字、年龄段、篇幅、期望教育寓意……")

# 用户是"点选问卷"而不是"打字"来提交需求时，输入框是空的，
# 这时把暂存的需求句取出来，当成这一轮的用户输入（两条入口合流到同一套流程）
if not user_input:
    user_input = st.session_state.pop("_pending_input", None)

# 用户真的发消息了（user_input 不是 None）才走下面的流程
if user_input:

    # ---- 6.2.1 立即把用户消息显示出来并记入列表 ----
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # ---- 6.2.2 从数据库读当前会话历史，拼成多轮对话上下文 ----
    history_text = format_history_text(safe_get_history(st.session_state.session_id))

    # ---- 6.2.3 【流式】调用智能体并展示回复 ----
    # 【为什么要流式】同步等待时，模型必须把整篇故事写完才一次性返回，每轮干等约 20 秒，
    # 页面上只有一个转圈 —— 台下看着像程序卡死。改成流式之后：
    #   ① 阶段提示实时告诉你"正在检索素材""正在存档"，看得见 Agent 在干活；
    #   ② 故事正文逐字长出来，像打字机一样，演示观感完全不同。
    with st.chat_message("assistant"):
        # 两个"渲染位置"（占位块）+ 一个结果暂存区：
        #   stage_ph —— 一行阶段提示（会被下一条提示覆盖）
        #   text_ph  —— 逐字长出来的故事正文
        #   state    —— 存流式结果。为什么用字典而不是普通变量？
        #              顶层脚本里没有"外层函数"，嵌套函数改不了外层的局部变量
        #              （写 nonlocal 会直接语法报错），所以用一个可变字典来装。
        stage_ph = st.empty()
        text_ph = st.empty()
        state = {"result": None, "text": "", "paint": 0.0}

        async def _consume_stream():
            """功能：消费智能体的流式输出，边收边往页面上刷
            【节流】模型每秒会吐几十个片段，每一片都刷新页面会把浏览器拖卡；
                   所以限制成最多每 0.1 秒刷一次，肉眼看到的依然是连续打字效果。
            """
            async for event in chat_stream(user_input, history_text,
                                           session_id=st.session_state.session_id):
                if event["type"] == "stage":
                    stage_ph.caption(event["text"])              # 阶段提示
                elif event["type"] == "delta":
                    state["text"] += event["text"]               # 累积正文
                    now = time.monotonic()
                    if now - state["paint"] > 0.1:
                        text_ph.markdown(state["text"] + " ▌")   # ▌ 当作打字光标
                        state["paint"] = now
                elif event["type"] == "done":
                    state["result"] = event["result"]            # 收齐最终结果

        with st.container():     # 本轮回复的元素统一收进这个容器里
            try:
                stage_ph.caption("🤖 智能体正在思考…")

                # 启动流式对话：asyncio.run 把异步生成器一次跑完，边跑边刷页面
                asyncio.run(_consume_stream())
                stage_ph.empty()          # 收工，清掉阶段提示

                result = state["result"]
                if result is None:
                    raise RuntimeError("智能体没有返回结果（流式输出意外中断）")

                answer = result.get("output", "")               # 最终回答
                steps = result.get("intermediate_steps", [])    # 工具调用过程列表

                # ---- 6.2.4 【兜底展示】防止"故事跑进数据库、页面上啥也没看到" ----
                # 【为什么需要这段】大模型偶尔会偷懒：把故事正文当作参数交给
                # story_db_tool 保存入库后，就以为"任务完成了"，最终回答里
                # 只写一句"故事已保存完成啦"，结果数据库里有全文、聊天区却是空的。
                # 【判断条件】① 本轮确实调用了保存动作（不能拿上一轮的故事顶包）
                #             ② 最终回答长度不足故事正文的 60%，说明正文基本没展示
                #                （0.6 是经验阈值：模型两次写正文时措辞会略有出入，
                #                 用绝对相等判断容易把"正常输出了正文"误判成"没输出"）
                # ③ 满足前两条时，就用 agent_service 记录的完整正文补到页面展示。
                # 【答辩可讲】这叫"容错设计"：不依赖大模型每次都听话，
                #             用一层代码保证演示效果稳定。
                display_text = answer          # 真正展示、也真正入库的文本
                # 本轮真正存进库的那篇故事（Agent 从请求级上下文带回来的，没存则为 None）
                last_story = result.get("saved_story")
                if (called_story_save(steps) and last_story
                        and len(answer) < len(last_story["story_content"]) * 0.6):
                    display_text = (
                        f"### 📖 《{last_story['story_title']}》\n\n"
                        f"**主角：**{last_story['main_role']}　｜　"
                        f"**适合年龄：**{last_story['age_group']}\n\n"
                        f"{last_story['story_content']}\n\n"
                        f"> 💡 **教育寓意：**{last_story['moral']}\n\n"
                        f"---\n\n{answer}"
                    )
                    st.caption("💡 智能体最终回答里没带故事正文（只回了收尾语），已自动从故事库补齐后展示")

                if result.get("clarify"):
                    # 澄清轮：给一句过渡提示。真正的"问卷"由消息列表渲染，
                    # 会在本轮结束重跑一次后出现（见下面 6.2.9），
                    # 这里不直接把文字清单铺出来，避免界面"先清单后问卷"闪一下。
                    st.caption("我来问几个小问题，点一下就好 👇")
                else:
                    # 正文已在流式过程中逐字显示，这里做"定稿"：去掉打字光标，
                    # 并且在触发兜底补齐时用完整版覆盖掉流式显示的版本。
                    text_ph.markdown(display_text)

                # ---- 6.2.5 【一致性核查】模型嘴上说"已存档"、实际却没存 → 自动补存 ----
                # 【为什么需要】实测发现：遇到"再长一点""扩写一下"这类追问时，
                # 模型可能跳过保存工具，却在回答末尾写"（这个故事已经帮您存档啦）"。
                # 用户去左侧「📖 历史故事」面板一查什么都没有 —— 这就是系统在撒谎，
                # 答辩演示时被老师问一句"存哪儿了？"就会当场翻车。
                # 【兜底做法】发现"声称已存档 + 本轮确实没调用保存工具"，
                # 就用最终回答自动补存一份，保证"说到"和"做到"一致。
                # 【答辩可讲】这是"输出一致性校验"，属于工程上防大模型幻觉的常见手段。
                saved_this_turn = called_story_save(steps)
                # 【参与这项核查的三个前提，缺一不可】
                #   ① 本轮必须是"创作轮"。寒暄/无关轮的回复里也常常出现"保存""存档"
                #      这类词 —— 比如介绍能力时说"我能把故事存进数据库"。若不区分意图，
                #      系统就会把聊天当成"模型漏存档"，**凭空多存一篇不存在的故事**；
                #   ② 不是澄清轮：澄清轮只问需求，本来就不该存故事；
                #   ③ 本轮确实**没有**调用存档工具。
                if (result.get("intent") == "create"
                        and not result.get("clarify")
                        and not saved_this_turn
                        and claims_saved(display_text)):
                    auto_title, auto_body = guess_story_from_answer(answer, user_input)
                    try:
                        DBUtil.save_story(
                            session_id=st.session_state.session_id,
                            story_title=auto_title,
                            main_role="未指定",        # 粗解析拿不到，留给用户自行判断
                            age_group="未指定",
                            story_content=auto_body,
                            moral="（模型未单独给出，见故事正文第三部分）",
                        )
                        st.caption(
                            f"⚠️ 智能体回答里提到「已存档」，但本轮并没有真的调用存档工具，"
                            f"系统已自动补存《{auto_title}》到故事库（可在左侧「历史故事」里查看）"
                        )
                    except Exception as save_error:
                        st.warning(
                            f"⚠️ 智能体回答里提到「已存档」但实际未入库，自动补存也失败了：{save_error}"
                        )

                # ---- 6.2.6 展示本轮「创作变奏」（防同质化机制的现场证据）----
                # 【为什么要展示】这是"故事为什么不再千篇一律"的可视化证据：
                # 系统每轮都会随机抽一组设定（主角类型 / 场景 / 叙事视角 /
                # 情节驱动 / 开头方式），拼成"变奏"注入提示词，逼模型换一套写法。
                # 展开这个面板，就能一眼看出"这次和上次不一样在哪"——答辩演示很直观。
                style_hint = result.get("style_hint", "")
                if style_hint and called_story_save(steps):
                    with st.expander("🎲 本轮创作变奏（系统随机生成的差异化设定，用来避免故事同质化）"):
                        st.markdown(style_hint)

                # ---- 6.2.7 展示 Agent 工具调用日志（课堂教学重点观察内容）----
                # 每个 step 是一个元组 (action, observation)：
                #   action.tool      是工具名；
                #   action.tool_input 是调用参数；
                #   action.log       是模型该步输出的消息（可能带思考文字）；
                #   observation      是工具返回结果
                # 【教学核心】这是 return_intermediate_steps=True 的成果兑现，
                # 也是回答"你怎么证明 Agent 真的调用了工具"的最佳证据。
                if steps:
                    st.divider()
                    st.caption("🔍 Agent 内部执行日志（教学观察：思考 → 调用工具 → 工具返回）")
                    for i, (action, observation) in enumerate(steps, 1):
                        with st.expander(f"第 {i} 步：调用工具「{action.tool}」"):
                            st.markdown("**① 工具输入参数**")
                            st.code(str(action.tool_input)[:500], language="text")
                            # action.log 有时为空（模型直接发起工具调用，没有写思考文字）
                            if action.log is not None and getattr(action.log, "content", ""):
                                st.markdown("**② 模型思考内容**")
                                st.markdown(str(action.log.content)[:500])
                            st.markdown("**③ 工具返回结果**")
                            st.code(str(observation)[:800], language="text")

                # ---- 6.2.8 把本轮问答保存到 MySQL ----
                # 单独包一层 try：保存失败只提示，不影响页面展示
                # 【设计亮点】双层 try：外层抓"智能体调用失败"，
                # 内层抓"对话保存失败"——保存失败只警告不崩溃，
                # 因为故事已经生成了，主任务优先。
                # 注意这里存的是 display_text（含补齐的故事正文）而不是 answer：
                # 这样下一轮对话读历史时，模型能看到上一篇故事的完整内容，
                # "续写故事/改结局"才真的接得上。
                try:
                    DBUtil.save_chat_history(st.session_state.session_id, user_input, display_text)
                except Exception as db_error:
                    st.warning(f"⚠️ 对话记录保存到数据库失败：{db_error}")

                # 把 AI 回复记入界面消息列表（下次刷新时还能看到）
                # 【clarify 标记】本轮是"需求澄清"回答（系统在问你想听什么故事），
                # 界面上要把它渲染成可点选的问卷，而不是普通的文字气泡。
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": display_text,
                    "clarify": bool(result.get("clarify")),
                })

                # ---- 6.2.9 【澄清轮的最后一步】重跑界面，让问卷显示出来 ----
                # 【为什么必须重跑】问卷是按"消息列表"渲染的（见第 6.1 步），
                # 而消息列表在本轮脚本开头就已经渲染过了 —— 现在才 append，
                # 这一轮没人再去渲染它。所以澄清轮必须重跑一次脚本。
                # 【为什么其它轮次不重跑】故事的正文、工具日志、变奏面板都是
                # 在本轮就地渲染的，重跑反而会把它们擦掉。只澄清轮需要。
                if result.get("clarify"):
                    st.rerun()

            except Exception as error:
                # 统一友好中文错误提示：
                # API超时、数据库异常、工具调用异常都会走到这里
                st.error(f"❌ {error}")
                st.caption("💡 常见原因：DeepSeek API 网络超时/密钥错误、MySQL 未启动、知识库未构建等")
