# MVP 架构

`app.py` 加载 `.env` 并启动仅监听本机的 HTTP 服务。`app/web.py` 提供上传、配置检查和 Excel 导出接口，并加载 `app/static/index.html`。上传接口接受一份或两份单据；页面更换文件时清除上一票核对结果。

提取流程在 `app/graph.py`：

1. `app/tools/document_reader.py` 将 PDF、Word、Excel 提取为文本。旧版 DOC、RTF、XLS 在 Windows 上通过 `legacy_extract.ps1` 调用本机 Office。
2. 无密钥时由 `app/nodes/rule_extract.py` 做保守的标签匹配；AI 模式由 `app/tools/ai_extract.py` 按 `prompts/booking_extraction.txt` 返回固定结构。Word 通过 `app/tools/layout_pdf.py` 转成保留版面的 PDF 与文字一同发送；原始 PDF 也作为页面输入。
3. 规则模式只使用本次实际上传的文件；两份都有时以入货通知字段优先，委托书补缺，两个值不同会在页面标记。AI 模式将冲突写入字段依据，业务员仍需核对。
4. 确认值由 `app/tools/excel_export.py` 填入 `assets/业务联系单模板.xlsx`，保持原模板样式。

AI 每个字段还返回 `source_label` 和 `review_reason`。业务员在核对页选择要记住的标签，导出后由 `app/tools/alias_memory.py` 保存到 `data/field_aliases.json`。记忆只包含标签到字段的对应关系，供之后的 AI 提取参考；不会保存本票的业务值。

国内起运港缩写在 `app/nodes/normalize.py` 中统一处理，规则和 AI 两种模式都会经过这一层。仅映射已确认的 QD、TJ，避免猜测其他港口缩写。

字段名称、模板单元格与项目路径集中在 `app/state.py`。新增字段时先更新那里，再调整规则、提示词、页面和测试。
