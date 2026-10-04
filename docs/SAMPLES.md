# 样例说明

## 当前公开版

`scripts/generate_samples.py` 生成虚构的 HTML、EML、CSV、TSV、XLSX、DOCX、PPTX、图片与 PDF。邮件使用 `example.com` 演示地址，文字与表格不涉及真实人员或业务数据。扫描 PDF 是把同一份虚构文本 PDF 渲染为图片后重新生成，确实没有原始文本层。

生成脚本随仓库提供，可检查样例制作过程。音频请自行提供，不随仓库分发来源不明的录音。`*_images/` 是解析时生成的图片目录，默认忽略。

## 本次整理前的素材

旧样例多数由仓库维护者从 GitHub 收集，但未记录每个文件的确切上游路径、版本与再分发许可。本次整理将 97 个原始样例及提取出的图片保留在本地 `.local-samples/workshops/`，该目录和 `.local-backups/` 不纳入公开版。此处理没有删除本地素材，也没有改写既有 Git 历史。

通过标题和可提取正文识别的旧 PDF 包括：

| 文件 | 可识别内容 |
| --- | --- |
| `layout-parser-paper-fast.pdf` / `layout-parser-paper-with-table.pdf` | LayoutParser 论文片段 |
| `rag-paper-2005.11401.pdf` | Retrieval-Augmented Generation 论文 |
| `multi-column.pdf` | Dense Passage Retrieval 论文 |
| `insider-threat-101-factsheet.pdf` | Insider Threats 101 宣传资料 |
| `ransomware-awareness-factsheet.pdf` | CISA 勒索软件风险宣传资料 |
| `embedded-images.pdf` | 车辆手册的免提卡使用说明片段 |

`c02-22.pdf`、`ccitt.pdf`、`multipage-6p.pdf` 为无文本层扫描样例；本次没有根据文件名认定内容或来源。

金融报告样例明确出现在 HTML 中：`example-10k-1p.html` 包含 Galaxy Gaming, Inc. 的 SEC 报告片段。标题识别只用于说明文件内容，不代表对任何文件的再分发许可作出确认。

将来重新引入第三方样例时，应记录来源链接、版本、适用许可和署名要求；能下载的文件不自动等于可以重新分发。
