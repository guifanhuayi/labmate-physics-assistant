# 管理员后台 Ant Design Pro 接入说明

日期：2026-10-27。用户已确认：管理员后台使用 Ant Design Pro；该要求已写入技术规格第 2.4 节与 README，后续管理员页面必须延续。

## 接入范围与边界

采用 [Ant Design Pro](https://github.com/ant-design/ant-design-pro) 的管理界面设计体系与官方 [ProComponents](https://github.com/ant-design/pro-components)，实际使用 ProLayout、PageContainer、ProTable、ProForm 和 Ant Design 组件，不是仅用 CSS 模仿外观。

Ant Design Pro 官方应用基于 React。项目现有 Vue 3 师生端保留：Vue Router 完成 `/admin` 的服务端身份恢复与角色检查后，动态加载 `AdminPage.vue`，再在管理员 Shadow DOM 内挂载独立 React 根节点。主应用不迁移、不另起 Umi 应用，也不把示例项目的路由、鉴权和 Mock 服务复制进正式系统。

固定依赖：

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| `@ant-design/pro-components` | 2.8.10 | 官方后台布局、查询表格与表单 |
| `antd` | 5.29.3 | 控件、弹窗、抽屉、反馈及中文语言包 |
| `@ant-design/cssinjs` | 1.24.0 | 将组件样式写入管理员 Shadow DOM |
| `react` / `react-dom` | 19.3.1 | 沿用现有 React 运行时，挂载管理员模块 |
| `@ant-design/v5-patch-for-react-19` | 1.0.3 | Ant Design 5 与 React 19 兼容 |
| `@types/react` | 19.3.0 | 管理员 TSX 类型检查 |

版本依据 npm 实际发布信息与 peerDependencies：本次 ProComponents 稳定版要求 Ant Design 4/5，故不混用 Ant Design 6。锁文件随依赖更新，后续升级重新检查兼容关系并做三类角色回归。

## 已接入业务

- 工作概览：从现有接口计算班级数、教师数和班级学生人次；同一学生可跨班，因此不将人次标为去重学生人数。
- 班级管理：搜索、教师筛选、排序、分页；管理员创建班级必须指定教师；查看班级学生及首次设置状态；删除前确认，保留原后端“有实验任务的班级不能删除、学生账号保留”规则。
- 名单导入：选择目标班级、选择 Excel/CSV、先预览、展示逐行错误、无错误后确认导入；切换班级/文件时废弃旧预览，避免导入错班。
- 教师目录：只读展示当前教师及其班级数，复用 `/api/teachers`，不提供不存在的教师增删改接口。
- 导航与退出：板块写入 `/admin?section=...`，刷新保留当前板块；沿用现有会话与退出 API。

后续账号维护、审计、系统配置等有真实接口后再增加；不得把示例按钮、随机数和演示图表当作已完成功能。本次不改变教师模板设计、Univer 集成或学生数据录入/提交规则。

## 隔离与权限约束

1. 管理员 React 模块只在 `/admin` 角色校验通过后动态加载；学生、教师入口不预载 Pro 依赖。
2. `mount.tsx` 创建开放 Shadow DOM；Ant Design reset、后台样式、CSS-in-JS 及 Select/Modal/Drawer 的弹层在该容器内。原全局按钮、输入框和圆角覆盖规则不能渗入后台；后台样式也不能影响学生手机/平板或教师表格。
3. Vue 卸载管理员页时调用 React `unmount` 并清理节点。原 Vue Router、Pinia、HttpOnly Cookie 和 FastAPI 授权为唯一权限链，前端菜单不替代服务端校验。
4. 管理员表单与表格复用 `frontend/src/api/client.ts` 中的 managementApi；请求继续使用同源 `/api` 与 `credentials: include`。不新增浏览器 Token 或另一份学生数据。
5. 后续新弹层也必须进入管理员容器，不能默认挂到 document.body 导致样式越界；新增学生端功能仍遵守手机/平板规范。

## 验证与代码入口

```powershell
cd frontend
pnpm build
pnpm test
pnpm e2e:admin
pnpm e2e:student
pnpm e2e:univer
```

浏览器验收使用模拟 API，不创建或删除真实班级。管理员用例覆盖原功能链路、错误名单不能提交、删除取消与确认、非管理员重定向及依赖按需加载；截图输出至 `frontend/test-results/`。学生和教师浏览器用例用于检查共享构建及样式隔离的回归。

2026-10-27 验证结果：生产构建通过，Vitest 25 项通过；管理员浏览器用例共 3 项通过，学生移动端 18 项通过、7 个不适用于移动项目的桌面切换用例按设计跳过，教师 Univer 用例 3 项通过。管理员完整业务、访问限制、弹窗失败信息、预览重复操作、退出卸载及回到登录页后的输入框样式均已验证。新增后台包单独分块，生产构建仍有大包体积提示；管理员首次加载需要下载该分块，学生入口未加载该模块。真实设备人工验收按学生端规范另行进行。

截图使用模拟账号和模拟 API：[工作概览](admin-pro-overview-preview-2026-10-27.png)、[班级管理](admin-pro-classes-preview-2026-10-27.png)。

代码落点：`src/pages/AdminPage.vue`（Vue 桥接）、`src/admin/mount.tsx`（挂载与样式隔离）、`src/admin/AdminConsole.tsx`（后台业务）、`src/admin/types.ts`（边界类型）、`src/admin/styles.css`（后台局部样式）、`src/router/index.ts`（管理员懒加载）、`e2e/admin-pro.spec.ts`（行为回归）。路径均相对 `frontend/`。

官方开源依赖使用 MIT 许可；静态资源的 `public/licenses/` 保留相应许可文本。没有复制整套 Ant Design Pro 示例仓库，也没有更换主应用的 Vue 或 FastAPI 运行方式。
