"""
======================================================================
db_util.py —— MySQL 数据库封装工具类（新手入门第 2 课）
======================================================================

【这个文件是干什么的？】
把项目里所有"操作 MySQL 数据库"的代码集中封装在一个类 DBUtil 里，
其他文件想存对话、存故事、查历史，只需要调用 DBUtil.xxx() 即可。

【为什么要封装？】
1. 避免重复：每个功能里都写一遍"连数据库、执行、关闭"会很啰嗦；
2. 统一异常：数据库连不上、SQL 写错等错误，统一转成中文友好提示，
   网页端可以直接展示给学生看；
3. 隐藏细节：业务代码不用关心连接怎么建立，只关心"存什么、查什么"。

【pymysql 操作数据库的标准五步（课堂必背）】
第 1 步 连接数据库：pymysql.connect(...)          —— 相当于打电话拨号
第 2 步 创建游标：conn.cursor()                    —— 相当于拿起听筒
第 3 步 执行 SQL：cursor.execute(sql, 参数)        —— 相当于说话（要查/存什么）
第 4 步 提交事务：conn.commit()（查询不需要提交）  —— 相当于确认执行
第 5 步 关闭连接：conn.close()                     —— 相当于挂电话
"""
import pymysql                    # MySQL 驱动库（pip install pymysql）
from pymysql.cursors import DictCursor  # 让查询结果以"字典"形式返回，方便用字段名取值

from src import config            # 导入全局配置（数据库账号密码都在 config 里）


class DBUtil:
    """MySQL 数据库工具类
    所有方法都是 @staticmethod 静态方法，
    调用方式：DBUtil.save_story(...)，不需要先创建对象。
    """

    # ------------------------------------------------------------------
    # 第 1 部分：私有方法 —— 创建数据库连接
    # 方法名带下划线开头（_connect），表示"内部专用"，外部代码不要直接调用
    # ------------------------------------------------------------------
    @staticmethod
    def _connect():
        """功能：创建一条到 MySQL 的连接
        入参：无（连接参数自动从 config 读取）
        返回：conn —— 数据库连接对象（连接失败时抛出带中文提示的错误）
        使用场景：每个增删改查方法的第一步都调用它
        """
        try:
            conn = pymysql.connect(
                host=config.MYSQL_HOST,         # 数据库地址（.env 里配置）
                port=config.MYSQL_PORT,         # 数据库端口（默认 3306）
                user=config.MYSQL_USER,         # 数据库账号
                password=config.MYSQL_PASSWORD, # 数据库密码（来自 .env，绝不硬编码）
                database=config.MYSQL_DB,       # 要操作的数据库名
                charset="utf8mb4",              # 字符集：必须 utf8mb4 才能存中文和 emoji
                connect_timeout=5,              # 连接超时 5 秒：连不上就赶紧报错，别傻等
                cursorclass=DictCursor,         # 查询结果用字典返回：row["字段名"] 取值
            )
            return conn
        except Exception as error:
            # 把底层英文报错包一层中文说明，学生一眼就知道问题出在哪
            raise RuntimeError(
                f"MySQL 数据库连接失败！请检查：\n"
                f"① .env 里的 MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD 是否正确；\n"
                f"② MySQL 服务是否已启动（Windows 服务里搜 MySQL）；\n"
                f"③ 是否已执行 sql/init.sql 建库建表。\n"
                f"原始错误信息：{error}"
            )

    # ------------------------------------------------------------------
    # 第 2 部分：测试方法 —— 验证数据库配置是否正确（课堂调试神器）
    # ------------------------------------------------------------------
    @staticmethod
    def test_connection() -> bool:
        """功能：测试数据库能否连上（只连接、不执行任何 SQL）
        入参：无
        返回：True —— 连接成功
        使用场景：配好 .env 之后先跑这个测试，确认数据库没问题再往下做
        """
        conn = DBUtil._connect()   # 连接失败会在这里直接抛出中文错误
        conn.close()               # 测试完立刻关闭，养成好习惯
        return True

    # ==================================================================
    # 第 3 部分：对话历史表 knowledge_chat_history 的操作
    # ==================================================================
    @staticmethod
    def save_chat_history(session_id: str, user_query: str, ai_answer: str):
        """功能：保存一条对话记录（用户问的一句话 + AI 回答）到对话历史表
        入参：
            session_id —— 会话ID（字符串）。同一次多轮对话共用同一个ID
            user_query —— 用户刚才输入的问题
            ai_answer  —— AI 回答的内容
        返回：无（保存失败会抛出中文错误）
        使用场景：网页里每完成一轮问答后调用，把对话持久化到数据库
        """
        # 写 INSERT SQL。%s 是"占位符"，真正的值稍后由 execute 传入。
        # 这样写能防止 SQL 注入（课堂会演示：直接把用户输入拼进 SQL 有多危险）
        sql = (
            "INSERT INTO knowledge_chat_history (session_id, user_query, ai_answer) "
            "VALUES (%s, %s, %s)"
        )
        # 五步曲第 1 步：连接数据库
        conn = DBUtil._connect()
        try:
            # 五步曲第 2 步：创建游标（with 写法会在代码块结束时自动关闭游标）
            with conn.cursor() as cursor:
                # 五步曲第 3 步：执行 SQL，把参数按顺序填入 %s 占位符
                cursor.execute(sql, (session_id, user_query, ai_answer))
            # 五步曲第 4 步：提交事务（INSERT 必须提交才真正写入数据库）
            conn.commit()
        except Exception as error:
            # 出错就回滚：撤销本次未完成的写入，保证数据不脏
            conn.rollback()
            raise RuntimeError(f"对话记录保存失败：{error}")
        finally:
            # 五步曲第 5 步：无论成功失败，都要关闭连接（finally 保证一定执行）
            conn.close()

    @staticmethod
    def get_chat_history(session_id: str, limit: int = 50):
        """功能：查询某个会话最近的对话记录（按时间正序返回）
        入参：
            session_id —— 要查询哪个会话
            limit      —— 最多查多少条（默认 50）
        返回：记录列表，每条是一个字典：{"user_query": ..., "ai_answer": ..., "create_time": ...}
        使用场景：① 网页切换会话时加载历史消息 ② 多轮对话时拼接上下文
        """
        sql = (
            "SELECT user_query, ai_answer, create_time FROM knowledge_chat_history "
            "WHERE session_id = %s ORDER BY id DESC LIMIT %s"
        )
        conn = DBUtil._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (session_id, limit))
                rows = cursor.fetchall()      # 取回全部查询结果（列表套字典）
            # 上面按 id 倒序取"最近 N 条"，这里反转回时间正序，
            # 这样返回的顺序就是"最早的消息排最前"，方便按顺序展示
            return list(reversed(rows))
        except Exception as error:
            raise RuntimeError(f"查询对话历史失败：{error}")
        finally:
            conn.close()

    @staticmethod
    def get_all_sessions():
        """功能：查询所有历史会话（按最近活跃时间倒序）
        入参：无
        返回：会话列表，每条是一个字典：
              {"session_id": ..., "last_time": 最近活跃时间, "msg_count": 消息条数}
        使用场景：网页侧边栏"切换历史会话"下拉框的数据来源
        """
        # GROUP BY session_id：按会话分组；MAX(create_time)：每组取最近一次时间；
        # COUNT(*)：统计每组消息条数
        sql = (
            "SELECT session_id, MAX(create_time) AS last_time, COUNT(*) AS msg_count "
            "FROM knowledge_chat_history GROUP BY session_id ORDER BY last_time DESC"
        )
        conn = DBUtil._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()      # 查询类操作不需要 commit
        except Exception as error:
            raise RuntimeError(f"查询会话列表失败：{error}")
        finally:
            conn.close()

    # ==================================================================
    # 第 4 部分：儿童故事表 children_story 的操作
    # ==================================================================
    @staticmethod
    def save_story(session_id: str, story_title: str, main_role: str,
                   age_group: str, story_content: str, moral: str):
        """功能：保存一篇生成完成的儿童故事到故事表
        入参：
            session_id    —— 故事属于哪个会话
            story_title   —— 故事标题
            main_role     —— 主角名字
            age_group     —— 适合年龄段（如 "3-6岁"）
            story_content —— 故事完整正文
            moral         —— 教育寓意
        返回：无（保存失败会抛出中文错误）
        使用场景：Agent 的故事持久化工具（story_db_tool）在生成故事后调用
        """
        sql = (
            "INSERT INTO children_story "
            "(session_id, story_title, main_role, age_group, story_content, moral) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        conn = DBUtil._connect()
        try:
            with conn.cursor() as cursor:
                # 6 个 %s 占位符，按顺序对应 6 个参数
                cursor.execute(sql, (session_id, story_title, main_role,
                                     age_group, story_content, moral))
            conn.commit()
        except Exception as error:
            conn.rollback()
            raise RuntimeError(f"故事保存失败：{error}")
        finally:
            conn.close()

    @staticmethod
    def get_all_stories(keyword: str = ""):
        """功能：查询全部故事（按保存时间倒序）；keyword 非空时按标题模糊搜索
        入参：
            keyword —— 标题关键词（选填）。例如 "小兔" 会查出标题里含"小兔"的故事
        返回：故事列表，每条是一个字典（含 story_title/main_role/age_group/
              story_content/moral/create_time 等全部字段）
        使用场景：① 网页"历史故事面板"展示全部故事 ② Agent 查询历史故事
        """
        conn = DBUtil._connect()
        try:
            with conn.cursor() as cursor:
                if keyword and keyword.strip():
                    # LIKE 模糊查询：% 表示"任意字符"。
                    # 注意 % 也是用参数化传入的（f"%{keyword}%"），不能直接拼进 SQL 字符串，
                    # 否则会有 SQL 注入风险（课堂上会演示对比）
                    sql = "SELECT * FROM children_story WHERE story_title LIKE %s ORDER BY id DESC"
                    cursor.execute(sql, (f"%{keyword.strip()}%",))
                else:
                    # 没传关键词就查全部
                    sql = "SELECT * FROM children_story ORDER BY id DESC"
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as error:
            raise RuntimeError(f"查询故事列表失败：{error}")
        finally:
            conn.close()
