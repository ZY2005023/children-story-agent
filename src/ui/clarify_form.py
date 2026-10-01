"""
======================================================================
clarify_form.py —— 需求澄清问卷（可点选的交互式选项卡片）
======================================================================

【这个文件是干什么的？】
用户的需求太模糊时（只说"写个故事""我要创作故事"，没给主题 / 主角 / 年龄），
不再甩一份"请回复编号（如 1A 2B 3B）"的文字清单让用户手敲，而是直接在聊天区
弹出这张问卷：

    主角是谁？                          1 / 4
    ○ 小动物
      小猫、小兔子、小刺猬这类会说话的小动物
    ○ 会说话的小物件
      小台灯、小雨伞、小汤勺这类身边的东西
    ...
    ⓘ 点一下选项就自动进入下一题          [全部跳过]

点一下卡片就选中，**选中即自动跳到下一题**（不用再点"下一步"）；
最后一题选中后自动开始创作。选"其他（自己写）"可以自己补充，
也可以"全部跳过"直接用默认值开写。答案会被拼成一句明确的需求，交给智能体直接创作。

【为什么分成四页而不是一页问完】
成熟产品的做法（参考问卷式向导）：每页只让用户做一个决定，注意力集中、
漏答率低；一页铺 4 组选项在手机上要来回滚，反而更容易放弃。

【"选中即跳"是怎么实现的（答辩可以讲）】
Streamlit 的控件支持 on_change 回调，它的执行顺序是：
    用户点击 → 控件值写入 session_state → 执行 on_change 回调 → 整个脚本重跑
也就是说回调跑在"重跑之前"，所以在回调里把"当前页号"改成下一页，
下一次重跑时读到的就是新页号 —— 天然完成翻页，不需要额外 st.rerun()。
唯一的例外是"其他（自己写）"：那一项后面还要填字，跳走就没法输入了，
所以选中它时不跳，等用户写完自己点"下一步"。

【和 agent_service.py 的分工（答辩可以这么讲）】
  · agent_service.classify_intent() 负责判断"要不要问"——意图路由，纯代码判定；
  · clarify_form.py 负责"怎么问、怎么收答案、怎么把答案拼成一句话"——交互与拼装。
  两者解耦：改问法不用动意图判定，改判定不用动界面。

【Streamlit 执行模型提醒】
用户每点一次，整个脚本从头重跑。所以"当前第几页""每题选了什么"这些
跨交互的数据必须放进 st.session_state，函数里用一个前缀 uid 把它们隔开，
避免不同会话 / 不同位置的问卷互相串状态。
"""
import streamlit as st


# ======================================================================
# 1) 题目定义
# ======================================================================
# 每一题：key（内部标识）/ title（题目）/ prompt_label（拼需求句时的字段名）
#        / default（跳过时用的默认值）/ options（选项：label 主文字 + desc 说明）
# label 里的 OTHER_LABEL 是特殊项：选中后要多显示一个输入框让用户自己写。
# 选项可选的 as_prompt：拼需求句时用它代替 label。
#        用途：界面上写"短一点"最简洁，但这句话传给模型时缺了量化标准，
#        实测模型会按自己的默认篇幅（约 500 字）写，等于没听用户的。
#        所以给这类"笼统说法"补一份带数字的版本，只用于拼需求句，不用于界面。
OTHER_LABEL = "其他（自己写）"

QUESTIONS = [
    {
        "key": "hero",
        "title": "主角是谁？",
        "prompt_label": "主角",
        "default": "小动物",
        "options": [
            {"label": "小动物", "desc": "小猫、小兔子、小刺猬这类会说话的小动物"},
            {"label": "会说话的小物件", "desc": "小台灯、小雨伞、小汤勺这类身边的东西"},
            {"label": "小朋友", "desc": "幼儿园里的小朋友，用真实生活场景"},
            {"label": OTHER_LABEL, "desc": "写下你想要的，比如「我家的大橘猫」"},
        ],
    },
    {
        "key": "moral",
        "title": "想讲什么道理？",
        "prompt_label": "想讲的道理",
        "default": "勇敢",
        "options": [
            {"label": "勇敢", "desc": "不怕黑、不怕生、愿意尝试新事物"},
            {"label": "分享", "desc": "把喜欢的东西分给别人，一起开心"},
            {"label": "诚实", "desc": "说实话、做错事敢承认"},
            {"label": "友爱或感恩", "desc": "关心家人朋友、谢谢别人的帮助"},
            {"label": OTHER_LABEL, "desc": "写下你想要的，比如「爱护小动物」"},
        ],
    },
    {
        "key": "age",
        "title": "给多大的孩子看？",
        "prompt_label": "适合年龄段",
        "default": "3-6 岁",
        "options": [
            {"label": "1-2 岁", "desc": "句子短、情节简单，画面感强"},
            {"label": "3-6 岁", "desc": "幼儿园阶段，最喜欢听故事"},
            {"label": "7-9 岁", "desc": "小学低年级，可以有一点小波折"},
            {"label": "10-12 岁", "desc": "小学高年级，情节可以更复杂"},
        ],
    },
    {
        "key": "length",
        "title": "篇幅多长？",
        "prompt_label": "篇幅",
        "default": "常规",
        "options": [
            {"label": "短一点", "desc": "约 200 字，睡前几分钟刚好讲完",
             "as_prompt": "短一点（全文 250 字以内，三个部分合计）"},
            {"label": "常规", "desc": "300~500 字，最常用",
             "as_prompt": "常规（全文 400 字左右）"},
            {"label": "长一点", "desc": "800 字以上，可以分成几个小段",
             "as_prompt": "长一点（800 字以上）"},
        ],
    },
]


# ======================================================================
# 2) 样式：把 Streamlit 自带的单选项改造成"可点选的卡片"
# ======================================================================
# 【为什么用 CSS 而不是自己画控件】Streamlit 没有原生的"带描述的单选卡片"，
# 但它渲染出来的单选项就是 <label> 元素，本身就是"整块可点击"的。
# 所以我们只用 CSS 给它加边框、圆角、内边距和选中高亮，
# 交互逻辑（单选、记忆状态）完全交给 Streamlit —— 稳、代码少。
#
# 【选择器怎么定的】不是凭空猜的，是查了 Streamlit 1.64 前端源码确认的：
#   · 单选组容器  → className="stRadio"         → div[data-testid="stRadio"]
#   · 选项组       → role="radiogroup"           （BaseWeb RadioGroup 生成）
#   · 每个选项     → 该组里的 <label>（即"整块可点"的那个元素）
#   · 选项文字     → label 内的 <p>（markdown 渲染出来的段落）
# 只覆盖外观（边框/底色/圆角），不改布局，尽量少跟框架的实现细节绑定。
#
# 【选中态】用 label:has(input:checked) 让整张卡片高亮（现代浏览器均支持）。
_CSS = """
<style>
/* 选项之间的纵向间距 */
div[data-testid="stRadio"] [role="radiogroup"] { gap: 0.5rem; }

/* 每张选项卡片 */
div[data-testid="stRadio"] [role="radiogroup"] label {
    width: 100%;
    box-sizing: border-box;
    padding: 0.75rem 1rem;
    border: 1px solid #e6e8ef;
    border-radius: 0.75rem;
    background: #ffffff;
    cursor: pointer;
    transition: border-color .15s ease, background .15s ease, box-shadow .15s ease;
}
div[data-testid="stRadio"] [role="radiogroup"] label:hover {
    border-color: #c9cee0;
    background: #fafbff;
}
/* 选中：整张卡片描边 + 浅蓝底 */
div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
    border-color: #6C7BFF;
    background: #f3f5ff;
    box-shadow: 0 0 0 1.5px #6C7BFF;
}
/* 第一行：选项主文字 */
div[data-testid="stRadio"] [role="radiogroup"] label p {
    margin: 0; font-size: 0.94rem; color: #1f2937; line-height: 1.4;
}
/* 第二行：选项说明（小一号、灰色） */
div[data-testid="stRadio"] [role="radiogroup"] label p + p {
    margin-top: 0.2rem; font-size: 0.8rem; color: #7a8092;
}
/* 题目、页码、底部提示、已选摘要 */
.cf-q { font-size: 1.02rem; font-weight: 600; color: #1f2937; padding-top: 0.15rem; }
.cf-page { text-align: right; color: #8b90a0; font-size: 0.85rem; padding-top: 0.45rem; }
.cf-hint { color: #8b90a0; font-size: 0.85rem; padding-top: 0.55rem; }
/* 已选摘要：自动翻页后让用户确认"前面我刚才选了什么" */
.cf-done { color: #8b90a0; font-size: 0.8rem; padding: 0.1rem 0 0.45rem 0; }
.cf-done b { color: #5b6377; font-weight: 600; }
</style>
"""


def _inject_css():
    """功能：把上面的 CSS 注入页面（每次渲染问卷时注入一次即可，重复注入无副作用）"""
    st.markdown(_CSS, unsafe_allow_html=True)


# ======================================================================
# 3) 把答案拼成一句"明确需求"
# ======================================================================
def compose_prompt(answers: dict, others: dict) -> str:
    """功能：把用户在问卷里的点选结果拼成一句需求描述，交给智能体去创作
    入参：
        answers —— {题目key: 选中的选项label}，例如 {"hero": "小动物", "moral": "分享"}
        others  —— {题目key: "其他"输入框里自己写的文字}
    返回：拼好的需求句，例如
          "请帮我创作一个儿童故事。主角：小动物；想讲的道理：分享；
           适合年龄段：3-6 岁；篇幅：常规。"
    使用场景：用户点「开始创作」或「全部跳过」时调用
    【为什么要拼成一句话】这样它就是一条"有具体内容"的输入，
          意图路由会直接判为明确需求（create），不会再弹第二次问卷。
          换句话说：跳过也都是有默认值的，绝不会陷入无休止的反问。
    """
    pieces = []
    for question in QUESTIONS:
        key = question["key"]
        value = (answers.get(key) or "").strip()

        # 选了"其他（自己写）" → 用输入框里的文字；没写就退回默认值
        if value == OTHER_LABEL:
            value = (others.get(key) or "").strip()

        # 没选 / 跳过的题目 → 用默认值补齐
        if not value:
            value = question["default"]

        # 命中预置选项且该选项带 as_prompt 时，换成带量化标准的说法。
        # 【为什么需要】界面上"短一点"够用，但模型看到三个字拿不准到底多短，
        # 实测会按自己的默认篇幅写。补成"短一点（约 200 字）"才真是听了用户的。
        for option in question["options"]:
            if option["label"] == value and option.get("as_prompt"):
                value = option["as_prompt"]
                break

        pieces.append(f"{question['prompt_label']}：{value}")

    return "请帮我创作一个儿童故事。" + "；".join(pieces) + "。"


def preview_defaults() -> str:
    """功能：生成"全部跳过时会用到的默认设定"一行文字（给用户看的小提示）
    返回：例如 "小动物 · 勇敢 · 3-6 岁 · 常规"
    """
    return " · ".join(q["default"] for q in QUESTIONS)


def answered_brief(answers: dict, others: dict, upto: int) -> str:
    """功能：把第 1 ~ upto 题里已经选好的答案拼成一行小字
    入参：
        answers —— {题目key: 选中的选项label}
        others  —— {题目key: "其他"输入框里自己写的文字}
        upto    —— 只统计到第几题（不含），即当前页之前的那些题
    返回：例如 "已选：小动物 · 分享"；一道都没答时返回空字符串
    使用场景：自动翻页后用户看不到上一页了，这行摘要让他能确认"我刚才选的是什么"，
              也方便发现点错（点「‹」回去改就行）。
    """
    parts = []
    for question in QUESTIONS[:upto]:
        value = (answers.get(question["key"]) or "").strip()
        if value == OTHER_LABEL:
            value = (others.get(question["key"]) or "").strip()
        if value:
            parts.append(value)
    if not parts:
        return ""
    return "<b>已选：</b>" + " · ".join(parts)


# ======================================================================
# 4) 自动推进：选中即翻页（on_change 回调）
# ======================================================================
def _on_option_pick(uid: str, step: int, question_key: str):
    """功能：单选项的 on_change 回调 —— 用户点一下卡片就自动进入下一题
    入参：
        uid          —— 问卷状态前缀（隔离不同问卷实例）
        step         —— 点击发生时在第几页（回调先于重跑执行，此刻页号还没变）
        question_key —— 这一题的内部标识
    返回：无（只改 session_state）
    使用场景：st.radio(on_change=_on_option_pick, args=(...)) 自动调用

    【执行时机】Streamlit 的顺序是"控件状态更新 → 回调 → 整脚本重跑"，
    所以这里改完 session_state，紧接着的那次重跑就能读到新页号，
    不需要再调 st.rerun()（多调一次反而白跑一轮）。

    【为什么不跳"其他（自己写）"】选中它之后还要在输入框里写字，
    页一翻输入框就没了。所以这一项故意不自动跳，等用户写完点"下一步"。
    """
    state = st.session_state
    chosen = state.get(f"{uid}_radio_{question_key}")

    # 没选 / 选了"其他" → 原地不动
    if not chosen or chosen == OTHER_LABEL:
        return

    # 顺手把答案存下来：本轮脚本重跑后 radio 的返回值就是它，
    # 但提前写一次更稳（不影响后续覆盖，值是一样的）。
    state.setdefault(f"{uid}__ans", {})[question_key] = chosen

    if step >= len(QUESTIONS) - 1:
        # 最后一题：置一个"待提交"标记，由 render_form 在重跑时翻译成"开始创作"
        state[f"{uid}__submit"] = True
    else:
        state[f"{uid}__step"] = step + 1


# ======================================================================
# 5) 问卷渲染主函数
# ======================================================================
def render_form(uid: str):
    """功能：渲染这套四步问卷（在聊天区里显示）
    入参：
        uid —— 状态前缀，用来隔离不同问卷实例的 session_state（避免串台）
    返回：str —— 用户点了「开始创作」或「全部跳过」时，返回拼好的需求句
          None —— 用户还在答题（没提交）
    使用场景：app.py 在"最后一条消息是问卷"时调用它
    """
    _inject_css()

    state = st.session_state
    k_step = f"{uid}__step"        # 当前第几页
    k_ans = f"{uid}__ans"          # 每题选了什么
    k_other = f"{uid}__other"      # "其他"输入框写了什么
    k_submit = f"{uid}__submit"    # 最后一题选完后由回调置位的"待提交"标记

    # 首次进入：初始化白板
    if k_step not in state:
        state[k_step] = 0
    if k_ans not in state:
        state[k_ans] = {}
    if k_other not in state:
        state[k_other] = {}
    if k_submit not in state:
        state[k_submit] = False

    step = int(state[k_step])
    total = len(QUESTIONS)
    question = QUESTIONS[step]

    # ---------------- 已选摘要（自动翻页后让用户确认前面选了什么）----------------
    brief = answered_brief(state[k_ans], state[k_other], step)
    if brief:
        st.markdown(f"<div class='cf-done'>{brief}</div>", unsafe_allow_html=True)

    # ---------------- 页头：题目 + 页码 + 左右翻页箭头 ----------------
    col_title, col_pager = st.columns([7, 3])
    with col_title:
        st.markdown(f"<div class='cf-q'>{question['title']}</div>", unsafe_allow_html=True)
    with col_pager:
        col_prev, col_num, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("‹", key=f"{uid}_prev", disabled=(step == 0), help="上一题"):
                state[k_step] = step - 1
                st.rerun()
        with col_num:
            st.markdown(
                f"<div class='cf-page'>{step + 1} / {total}</div>",
                unsafe_allow_html=True,
            )
        with col_next:
            if st.button("›", key=f"{uid}_next", disabled=(step == total - 1), help="下一题"):
                state[k_step] = step + 1
                st.rerun()

    # ---------------- 选项卡片（单选） ----------------
    # options 用 label 当"值"（返回值干净，便于拼需求句），
    # format_func 负责把 label 显示成"主文字 + 空行 + 说明"两段式。
    options = [opt["label"] for opt in question["options"]]
    display = {
        opt["label"]: (opt["label"] if not opt["desc"] else f"{opt['label']}\n\n{opt['desc']}")
        for opt in question["options"]
    }
    saved = state[k_ans].get(question["key"])
    default_index = options.index(saved) if saved in options else None

    chosen = st.radio(
        question["title"],                       # 给屏幕阅读器用的标签（界面上隐藏）
        options,
        index=default_index,                     # None = 默认不选中（必须用户自己点）
        format_func=lambda x: display[x],
        key=f"{uid}_radio_{question['key']}",
        label_visibility="collapsed",
        # 【选中即翻页】点一下就走，不用再点"下一步"。回调定义见 _on_option_pick。
        on_change=_on_option_pick,
        args=(uid, step, question["key"]),
    )
    if chosen:
        state[k_ans][question["key"]] = chosen
    else:
        state[k_ans].pop(question["key"], None)   # 取消选择也要同步清掉

    # 选了"其他（自己写）"→ 出现一个输入框
    if chosen == OTHER_LABEL:
        text = st.text_input(
            "补充内容",
            value=state[k_other].get(question["key"], ""),
            key=f"{uid}_other_{question['key']}",
            placeholder="用一句话写下来，比如：我家的大橘猫",
            label_visibility="collapsed",
        )
        state[k_other][question["key"]] = text

    # ---------------- 底部操作栏 ----------------
    # 【现在只剩两种需要动手的情况】① 选了"其他（自己写）"，写完要点一下继续；
    # ② 回退到前面某一页看完想直接前进（不改答案时 on_change 不会触发）。
    # 其余情况都会自动翻页，"下一步"按钮只是兜底，不用它也行。
    other_text = (state[k_other].get(question["key"]) or "").strip()
    answered = bool(chosen) and (chosen != OTHER_LABEL or bool(other_text))
    is_last = (step == total - 1)
    go_label = "开始创作" if is_last else "下一步"

    col_hint, col_skip, col_go = st.columns([5, 1.6, 1.8])
    with col_hint:
        if not chosen:
            st.markdown(
                "<div class='cf-hint'>ⓘ 点一下选项就自动"
                + ("开始创作" if is_last else "进入下一题") + "</div>",
                unsafe_allow_html=True,
            )
        elif not answered:
            st.markdown(
                f"<div class='cf-hint'>ⓘ 选了「其他」，写好后点{go_label}</div>",
                unsafe_allow_html=True,
            )
    with col_skip:
        skip_clicked = st.button("全部跳过", key=f"{uid}_skip", use_container_width=True,
                                 help=f"直接用默认设定开写：{preview_defaults()}")
    with col_go:
        go_clicked = st.button(
            go_label,
            key=f"{uid}_go", type="primary", use_container_width=True,
            disabled=not answered,
        )

    # ---------------- 按钮响应 ----------------
    if skip_clicked:
        # 全部跳过：所有题目都用默认值拼成需求句（保证不会陷入反复追问）
        return compose_prompt({}, {})
    if go_clicked:
        if is_last:
            return compose_prompt(state[k_ans], state[k_other])
        state[k_step] = step + 1
        st.rerun()

    # ---------------- 最后一题"选中即提交" ----------------
    # 回调在最后一题选中时置了标记，这里把它翻译成"开始创作"。
    # 放在按钮响应之后：万一用户是点按钮提交的，标记本就没置位，互不干扰。
    if state.pop(k_submit, False):
        return compose_prompt(state[k_ans], state[k_other])

    return None


def reset_form(uid: str):
    """功能：清掉这套问卷的所有状态（用户提交后调用，避免残留状态影响下一次问卷）
    入参：
        uid —— 和 render_form 用同一个前缀
    返回：无
    """
    for suffix in ("__step", "__ans", "__other", "__submit"):
        st.session_state.pop(f"{uid}{suffix}", None)
    # 控件的 key 交给 Streamlit 自己清理（它们随本轮未渲染而失效）
