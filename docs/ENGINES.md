# 引擎选型与官方接口

资料查阅日期：2026-10-04。目标是文档结构质量、实用部署与可追溯输出，不是宣称某个模型适合所有任务。本轮仅修改源代码，未安装依赖、下载权重或验证推理。

| 任务 | 采用方案 | 官方依据 |
| --- | --- | --- |
| PDF | MinerU 4 standard / advanced | [Python SDK](https://opendatalab.github.io/MinerU/usage/sdk_api/)、[输出与资源保存](https://opendatalab.github.io/MinerU/reference/output_files/)、[官方 GitHub](https://github.com/opendatalab/MinerU) |
| 图片文档、表格与公式 | PaddleOCR-VL 1.6 | [官方 Python 接口、模型和部署说明](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md) |
| Office、HTML、邮件、表格 | Docling | [官方 GitHub](https://github.com/docling-project/docling)、[格式支持](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md)、[邮件后端](https://github.com/docling-project/docling/blob/main/docling/backend/email_backend.py) |
| 音频 | Qwen3-ASR-1.7B + ForcedAligner-0.6B | [官方 GitHub 与调用示例](https://github.com/QwenLM/Qwen3-ASR) |

## 接入约定

MinerU 使用 4.0 的 mineru.parser.parse，不沿用旧 CLI backend 参数。默认解析全部页面，通过 FileBasedDataWriter 保存结果。standard 用于常规 PDF，advanced 用于复杂页面。原始结构完整保留；通用块转换遇到陌生结构时保留 JSON 表示，供后续细化。

PaddleOCR-VL 显式指定 pipeline_version="v1.6"，开启图表识别。每页原始 JSON 和 Markdown 单独保存，区域类型、内容和坐标进入统一分块。不把这一流程描述成一般照片或视频理解。

Docling 使用 DocumentConverter 与原生格式后端。表格导出 Markdown，图片保留题注或结构引用；部分成功也会报错，避免把缺失内容当作完整结果。TSV 转 CSV 使用标准库，只做容器适配。

Qwen3-ASR 使用 1.7B 开源权重，并通过 0.6B ForcedAligner 对齐。请求对齐但无时间信息时会报错；可显式传 timestamps=False 仅输出全文。words 保留词级原文和时间；展示文本用空格连接词项，中文空格可按下游需要规范化。未实现说话人分离。

## 环境与版本

建议各引擎独立环境。依赖文件为选型范围，并非已验证的完整锁文件；安装时使用 -U，尤其注意邮件后端和 v1.6 管线需要新版发行包。若发行包尚未包含官方主线接口，应参考对应仓库的源码安装说明；本仓库不自动下载源码或切换引擎。

模型加载仅发生在显式调用适配器时。运行时、模型权重及许可证分别参考上游。本仓库没有打包第三方权重，也没有承诺不同框架在同一环境中兼容。
