# 业务联系单生成助手 MVP

本地运行的演示程序：上传同一票的订舱委托书、入货通知中的任意一份或两份，核对提取出的 8 个字段，再下载保留原版格式的 Excel 业务联系单。文件中缺少的字段可在核对页参考订舱聊天或邮件手动填写；承运公司、合约可手填，客服和揽货人可从英文名名单中选择。

## 启动

需要 Python 3.10 以上。旧版 `.doc/.rtf/.xls` 在 Windows 使用本机 Microsoft Office，在 Linux 服务器使用 LibreOffice 无界面转换；PDF、DOCX、XLSX 的规则文字提取无需 Office。AI 模式下 Word 版面转换在 Linux 也依赖 LibreOffice。

```powershell
cd C:\Users\Administrator\Documents\Codex\2026-09-26\lai\ASW-Project01\ASW-Project01
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/manage_users.py add admin
.\.venv\Scripts\python.exe app.py
```

在浏览器打开 <http://127.0.0.1:8765>。
首次在本机打开时，页面会提示设置管理员账号和至少 12 位的密码；也可预先用上面的命令在终端创建账号。服务器部署模式禁用页面首次设置，必须先在服务器终端创建账号。

## 多人使用前的安全配置

管理员在服务器终端运行 `scripts/manage_users.py add 用户名` 创建个人账号；不要共用账号或在聊天里发送密码。密码使用逐账号随机盐的 scrypt 哈希；连续失败 5 次后暂停该账号登录 15 分钟。会话最长 8 小时、空闲 30 分钟过期；退出登录立即失效。HTTP API 均要求登录，写操作还需要 CSRF 校验。任务结果、AI 配置、纠错记忆和本次运行统计按账号隔离。审计库只记录账号、时间、事件和结果，不记录单据正文或 API Key。

AI Key 在数据库中用 Fernet 加密。单机首次使用会生成 `data/security.key`；正式部署须通过环境变量 `ASW_MASTER_KEY` 提供主密钥，并设置 `ASW_REQUIRE_EXTERNAL_KEY=1`，不得把主密钥提交 Git 或与数据库放在相同权限域。失去主密钥后无法解密现有 AI 配置。旧版仅在进程内存的 AI Key 无法迁移，升级后需在登录页面重新测试并保存。

备份：`.\.venv\Scripts\python.exe scripts/backup_data.py D:\受保护的备份目录`。备份包含账号数据库、每用户纠错记忆，以及本地生成的主密钥；必须限制备份目录访问、定期转移到独立存储并测试恢复。使用外部 `ASW_MASTER_KEY` 时需单独安全备份该环境密钥。恢复时先停服务，校验备份数据库完整性，再恢复 `data/security.sqlite3`、`data/users/` 和本地主密钥文件，重启后登录验证。

上传只接受指定扩展名及相符文件结构，每份最多 12 MB；Office 压缩文件有解压尺寸和条目数限制。程序仍只监听 `127.0.0.1`。阿里云服务器通过 Nginx 的 HTTPS 入口访问，部署位置、证书续期与回退方法见 [任务六部署与回退](docs/任务六部署与回退.md)。

默认是“规则演示”模式，不需要 API 密钥。此模式只针对常见标签做保守提取，适合演示上传、核对和导出完整流程；复杂版式可能留空，需人工确认。

每个上传框都可单独移除文件，也可使用“清空已选文件”开始处理下一票。更换文件后，上一票的核对结果会立即清除。

提取后的核对页会集中列出待补充、来源冲突与需要人工核实的字段；点击提示可定位到输入框，人工填写后自动更新，冲突或疑义可手动标记“已核对”。清单只辅助审核，不代替对照原件；即使仍有待核项也可下载，但页面会提醒转交前确认。

页面显示当前账号在本次服务运行中的提取统计：完成/失败票数、成功任务平均耗时，以及成功任务中 8 个目标字段的非空填充率（不代表准确率）。提取时会按实际执行阶段显示读取单据、准备提取、识别字段、整理结果、完成，并显示实时耗时及阶段记录。统计只保存在内存里，重启服务清零；原始上传文件不落盘，任务结果在内存中最多保留 15 分钟供页面读取。

## 启用 AI 提取

选择页面上的“AI 提取”后，设置表单才会出现。填写 `base_url`（接口根地址）、`api_key` 和 `model`，点击“测试连接并保存”。测试会向该模型发送一条简短消息，只有成功才会启用 AI 提取；可能产生少量厂商费用。页面不会回显密钥；密钥按账号加密保存在服务器数据库中，不写入仓库或浏览器存储。点击“清除配置”可立即停用。

示例：OpenAI 的 `base_url` 为 `https://api.openai.com/v1`；DeepSeek 的为 `https://api.deepseek.com`。不要在根地址后添加 `/responses` 或 `/chat/completions`。官方 OpenAI 地址使用 Responses API，可发送单据文字及 PDF 版面；Word 文件会先在本机临时转换为 PDF。DeepSeek 官方地址配合 `deepseek-flash` 时，会把每份 PDF 的前 3 页在本机转成页面图像后发送给模型，即使 PDF 是扫描件也能尝试识别；图像输入可能增加费用，超过 3 页的部分须人工核对。其他兼容地址或模型仍只发送本机读取的文字，扫描件可能无法识别。所有模式都必须人工核对。AI 服务的区域、权限、费用和模型可用性以厂商账户为准。

如果连接测试出现 `WinError 10061`，先检查启动程序的环境是否把 `HTTPS_PROXY` 指向了未启动的本机代理。本项目曾遇到 `127.0.0.1:9`：这会在验证 API Key 或模型前直接拒绝连接。修复代理，或从没有该失效代理设置的正常网络环境启动程序；不要因为连接错误就反复更换密钥。页面会在可识别时显示代理地址，密钥不会出现在错误提示中。

请先确认公司允许上传相应客户单据。应用不长期保存上传文件；不要把密钥提交到 Git。`.env` 现在只用于可选的本地端口配置，不再加载 AI 密钥。

AI 会在核对页显示字段原文标签与依据。“核对后记住标签”默认不勾选；只有人工勾选并下载 Excel 后，标签到业务字段的映射才会按账号保存在 `data/users/<内部账号编号>/approved_memory.json`。修改字段会自动取消勾选。AI 设置里可“查看记忆”、撤销标签映射，并主动批准或撤销固定的箱型格式规则。`data/field_aliases.json` 仅作为已审核的初始标签表；后续个人记忆文件已加入 Git 忽略列表，不会随普通提交推送。系统不保存提单号、客户信息等本票业务值；该记忆只是下次提取的参考，不会训练或修改模型本身。

## 字段与规则

写入模板的单元格：B8 提单号/订舱号，B9 船名，E9 航次，B10 船期，B11 箱量及类型，B12 场站，B13 目的港，E13 起运港。提取时以入货通知为优先，委托书用于补缺；缺失保持空白。船期优先取起运港预计开船日或 ETD；多程运输不把首程船 ETA 当作船期，特殊票由人工修改。国内起运港按已确认的简称显示：QINGDAO 为 QD，TIANJIN 为 TJ；其他港口暂保留原文。

模板位于 `assets/业务联系单模板.xlsx`。程序只绑定 `127.0.0.1`，公网访问由服务器的 HTTPS 反向代理提供。

## 项目结构

```text
app.py                  启动入口
app/wsgi.py             当前网页与 HTTP 接口
app/web.py              旧版 HTTP 兼容入口（不用于服务器启动）
app/graph.py            两份单据的处理流程
app/state.py            字段和模板单元格映射
app/nodes/              规则提取节点
app/tools/              文档读取、AI 提取、Excel 导出
app/static/             网页界面
app/business.py         公司字段、人员与港口配置
app/models.py           单据与字段结果数据模型
app/services/           请求验证、流程编排、合并、审核导出
app/rules/              有序的字段匹配规则
prompts/                AI 提取提示词
data/                   人工确认的字段别名
assets/                 业务联系单原版模板
tests/                  回归测试
docs/architecture.md    结构与扩展说明
```

重构后的模块职责见 [架构说明](docs/architecture.md)。人员名单集中在 `app/business.py`，日期、目的港与起运港统一规范化；诊断日志位于 `logs/app.log`，不写入 API Key 或单据正文。`build/`、`dist/` 和日志均不提交 Git。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如开发电脑安装了 Node.js，还可运行 `node tests/test_frontend.cjs`，检查前端网络重试策略。Node.js 只用于该项开发测试，不是程序运行依赖。

新增的 [盲测说明](docs/测评方法.md)介绍如何在仓库外保存真实单据和标准答案，并使用 `python evaluate_cases.py 私有清单.json` 统计规则提取的漏填、误填和整票准确情况；该结果不代表 AI 提取准确率。
