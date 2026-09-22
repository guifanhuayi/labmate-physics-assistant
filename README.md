# LabMate 物理实验数字助手

LabMate 正在从静态交互原型升级为 Vue、FastAPI 和 PostgreSQL 驱动的真实系统。当前已完成开发阶段 0～3 的纵向切片：真实账号与角色权限、班级与 Excel/CSV 名单导入、可视化实验模板设计、白名单计算校验、不可变模板版本以及班级实验任务发布。

## 当前目录

- `frontend/`：Vue 3、TypeScript、Vite、Pinia 和 Router 前端。
- `backend/`：FastAPI、SQLAlchemy 和 Alembic 后端。
- `deploy/`、`compose.yaml`：本地 PostgreSQL 与全栈开发环境。
- `dist/`：迁移期保留的静态演示原型，不参与新系统的数据与权限判断。
- `docs/voltage-resistance-acceptance.md`：阶段 0 的伏安法测电阻验收样例。

## 本地启动

前置条件：Docker Desktop 已安装并正在运行。

1. 将 `.env.example` 复制为 `.env`，为数据库和三种角色分别设置本地开发密码。密码至少 12 位并同时包含字母和数字。
2. 启动完整环境：

   ```powershell
   docker compose up --build -d
   ```

3. 首次创建匿名开发账号：

   ```powershell
   docker compose exec api python -m app.seed
   ```

4. 打开 <http://localhost:5173>。本地 Compose 默认开启演示登录，账号和密码可填写任意内容，也可以全部留空：
   - 学生：`20260001`
   - 教师：`t0001`
   - 管理员：`admin`

   输入 `admin` 或 `t0001` 可体验对应角色，其他账号统一进入学生工作台。当前开发阶段不强制首次改密，也不限制失败次数。设置 `DEMO_AUTH_ENABLED=false` 后恢复真实密码验证、账号状态和登录限流。

停止环境：

```powershell
docker compose down
```

只需在本机预览已经构建好的前端时，也可以使用轻量启动器。它会在同一端口提供 Vue 页面、FastAPI 接口和 SQLite 演示数据，并支持直接刷新 `/teacher` 等前端路由：

```powershell
cd backend
.\.venv\Scripts\python.exe preview_server.py
```

随后打开 <http://127.0.0.1:8010/>。

## 验证

后端测试使用独立的真实 PostgreSQL 数据库 `labmate_test`：

```powershell
docker compose exec api pip install -e ".[dev]"
docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://labmate:$env:POSTGRES_PASSWORD@db:5432/labmate_test api pytest
```

前端测试与构建：

```powershell
docker compose exec web pnpm test
docker compose exec web pnpm build
```

API 文档位于 <http://localhost:8000/api/docs>。

## 当前功能范围

- 教师可创建自己负责的班级；管理员可为指定教师创建班级。
- 名单支持 `.xlsx` 和 `.csv`，既接受“学号、姓名、班级代码、班级名称、学期”标准格式，也接受“姓名、学号、班级”紧凑格式；目标班级负责补齐班级代码、名称和学期。系统先预览并逐行校验，再通过数据库事务确认导入，错误名单不会污染用户或班级成员数据。
- 教师可从“力学综合实验”预设或空白模板开始，可视化配置实验目标、预习问题、操作步骤、多张数据表、字段单位与范围、受控计算、图表和提交要求，无需编写 JSON 或公式代码。
- “力学综合实验”预设由真实实验报告整理而来，包含不同振幅周期、不同质量周期、弱阻尼平衡位置速度和速度峰值变化四组数据记录。
- 后端负责步骤与数据表标识、字段、精度、范围、计算依赖、坐标轴和受控函数白名单校验。
- 模板发布生成只读快照；后续修改只影响草稿，再发布时形成新版本。
- 教师可选择已发布模板版本和自己负责的班级发布实验任务，并在工作台查看已发布任务及其班级、模板版本和时间范围。

学生动态表格、IndexedDB/服务器双重自动保存和正式提交属于阶段 4～5，尚未迁入新系统。

## 安全说明

- 浏览器只保存默认有效期 30 天的 `HttpOnly` 会话 Cookie，不再通过 `sessionStorage` 推断角色。
- 账号与密码自动填充由浏览器密码管理器负责，网站不会把明文密码写入前端存储。
- 密码使用 Argon2id 摘要，数据库不保存明文密码。
- 后端统一执行角色授权；前端路由守卫只改善体验，不能代替服务端权限。
- 安全模式下连续失败达到五次后，账号登录会暂时限流 15 分钟；本地演示模式不累计失败次数。
- 当前只使用匿名开发账号，禁止写入真实师生密码或个人信息。
