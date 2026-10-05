# MVP 架构与维护边界

本次重构基于 main 的 70e9937，没有合入 ASW-V1 的 exe 启动器，也不引入数据库、登录或邮件扫描。仍仅监听本机，现有提取、配置、任务和导出接口保持兼容。

## 数据流

```text
浏览器 → web.py（HTTP 边界、静态资源）
       → services/requests.py（上传验证）
       → jobs.py（本次运行的任务、进度与统计）
       → graph.py（兼容入口）→ services/extraction.py
         → tools/document_reader.py（文件读取）
         → nodes/rule_extract.py 或 tools/ai_extract.py
         → services/merge.py（规则结果来源优先级、冲突判断）
         → nodes/normalize.py（统一业务显示格式）
       → 人工审核 → services/export.py → tools/excel_export.py
```

AI 一次处理同票文件，来源优先级和冲突提示仍由提示词指导；规则模式由 merge 服务执行来源策略。两者并未共用同一合并算法。

## 文件职责

- business.py：字段名称、Excel 单元格、人员名单、已确认的港口简称、箱型等价关系。人员变动无需修改 JavaScript。
- models.py：单据、字段和提取结果模型；对外仍序列化为字典。raw_value 保留进入统一规范化前的引擎结果，不等同于完整原件内容，原文核对使用 evidence。
- state.py：路径与上传大小，兼容旧调用的字段常量由 business 派生。
- services/：与 HTTP 无关的验证、流程、合并和导出；流程不修改调用方传入的单据字典。
- rules/patterns.py：有顺序的字段表达式；首个明确匹配优先。特殊表格、船名航次拆分仍在规则引擎中，不把复杂正则强行配置化。
- tools/：文档库、Office 转换、AI 请求和文件持久化。旧版 Office 文件仍依赖 Windows Microsoft Office。
- static/：HTML 为结构，CSS 为样式，api.js 为请求，ui.js 为控件，review.js 为审核表单，app.js 为配置、进度与页面流程。

规则和 AI 都经过同一规范化函数，重复调用不会继续改变值。国内港口只用确认过的映射，目的港只去除已知国家后缀。箱型显示保留允许的 GP/DV、HQ/HC 写法，冲突比较使用等价关系，不把普通冷柜误判为 NOR。

## 运行状态与诊断

当前仍为单机、单用户 MVP。AI 配置、任务和统计在进程内存，重启清空；最多同时两票，结果最多保留 15 分钟。尚无多用户隔离，不能直接作为多人生产系统。

新增 /api/review-config 提供字段标签与人员名单，不含密钥；静态资源使用白名单路由，禁止任意文件路径读取。

logs/app.log 为轮转日志，只记录固定事件、任务 ID、异常类型和堆栈位置，不记录密钥、正文、业务值、异常消息或源码行。日志写入失败不影响业务；它不是完整审计系统，不保证捕获原生崩溃或浏览器拦截。

浏览器对连接失败的 GET 最多尝试 3 次；POST 不自动重试，避免重复提交单据。这不代表已经定位或修复老板电脑上的 Failed to fetch。

## 测试与扩展

运行：`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`。

前端请求策略测试：`node tests/test_frontend.cjs`；Node.js 仅用于开发测试。

原有 33 项测试原样保留，按规则、AI、读取、任务、导出拆分。新增服务及 HTTP 集成测试使用合成 DOCX/XLSX，不上传客户原件、不调用收费 AI。真实案例目前主要覆盖整理后的文本，不等同于全部原始单据的端到端测评。

新增字段：修改 business 定义、规则或 AI schema/提示词、规范化及测试；审核页自动获取字段配置。新增文件格式：修改读取适配器和支持格式列表，再加实际文件测试。新增 AI 协议：在 provider/AI 适配层扩展，不改审核和导出。

后续可逐步拆出特殊模板规则、AI 适配器接口和任务存储接口。数据库、账号与权限作为独立阶段设计，不能直接沿用当前全局配置。
