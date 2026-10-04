# Document Cleaning & Extraction

**用 MinerU、PaddleOCR-VL、Docling 与 Qwen3-ASR，把多格式资料转为可追溯的文档块。**

本项目按输入类型选择解析引擎，处理文档版面、扫描文字、原生结构和音频转写，统一导出 Markdown、原始结构与供检索使用的 JSON 分块。

> 当前状态：已按上游官方接口迁移代码和 10 个 Notebook；本次未下载模型、未运行推理或测试。下表描述接入方案，不代表本仓库实测的效果或性能。

## 处理方式

| 输入 | 当前引擎 | 处理路径 | 示例 |
| --- | --- | --- | --- |
| 有文字层的 PDF | **MinerU 4 / standard** | 版面与内容解析 → 结构化页面 → Markdown、页码及分块 | [文本 PDF](workshops/pdf/纯文本.pdf/clean-pure-text.ipynb) |
| 扫描 PDF | **MinerU 4 / advanced** | OCR 与版面解析 → 页面内容块 → 保留页码和原始结构 | [扫描 PDF](workshops/pdf/扫描.pdf/clean-scan-pdf.ipynb) |
| 图文混排 PDF | **MinerU 4 / advanced** | 解析正文、表格、公式与图片区域，保存生成的资源 | [混排 PDF](workshops/pdf/图文混排.pdf/clean-mixed-pdf.ipynb) |
| 图片、拍照文档 | **PaddleOCR-VL 1.6** | PP-DocLayoutV3 + PaddleOCR-VL-1.6-0.9B；区域识别、表格与公式内容，开启图表识别 | [图片](workshops/img/clean-image.ipynb) |
| Word / DOCX | **Docling** | 原生结构转换，提取段落、表格、图片题注和来源引用 | [Word](workshops/word/clean-pure-text.ipynb) |
| PowerPoint / PPTX | **Docling** | 幻灯片内容转换，保留引擎提供的结构与定位信息 | [PPT](workshops/ppt/clean-ppt.ipynb) |
| HTML | **Docling** | 本地 HTML 转为统一文档结构与 Markdown | [HTML](workshops/html/clean-html.ipynb) |
| 邮件 / EML、MSG | **Docling email backend** | 邮件内容转换，依赖 format-email 扩展 | [邮件](workshops/email/clean-email.ipynb) |
| CSV / TSV / XLSX | **Docling** | 结构化表格转换；TSV 先规范为 CSV，再进入同一引擎 | [表格](workshops/xlsx/clean-data.ipynb) |
| 音频 | **Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B** | 转写 → 词级时间对齐 → 约 30 秒片段 → 文本分块 | [音频](workshops/media/clean-audio.ipynb) |

PDF 默认路由到 MinerU standard；复杂 PDF Notebook 显式选择 advanced。图片默认路由到 PaddleOCR-VL，也可显式选择 MinerU。失败会直接报错，不会静默切换解析器。

选型兼顾结构质量、任务适配和部署方式，不宣称某个模型在所有文件、语言和硬件上都最好。Docling 是文档工具链，Office 原生结构适合直接解析，无需全部截图后交给视觉模型。官方依据见 [选型与接口说明](docs/ENGINES.md)。

## 使用

建议为各引擎分别准备 Python 3.12 环境，按官方说明选择设备对应的运行时。以下命令供使用者主动执行，本次迁移没有执行安装或推理。

```bash
git clone https://github.com/cwj-66/Document-cleaning-extraction.git
cd Document-cleaning-extraction
python -m venv .venv
```

激活环境后，**只安装本次要用的引擎**：

| 任务 | 依赖文件 | 额外准备 |
| --- | --- | --- |
| PDF / MinerU | `requirements-pdf.txt` | 按官方说明准备 standard / advanced 的运行时和权重 |
| Office、网页、邮件、表格 | `requirements-documents.txt` | 新版 Docling；邮件扩展已列入依赖 |
| 图片 / PaddleOCR-VL | `requirements-image.txt` | 匹配设备的 Paddle 推理运行时及模型 |
| 音频 / Qwen3-ASR | `requirements-audio.txt` | 匹配的 PyTorch、ASR 与对齐模型；默认 cuda:0 |

例如安装 PDF 依赖，在运行时和权重就绪后执行：

```bash
python -m pip install -U -r requirements-pdf.txt
python -m document_cleaning "workshops/pdf/纯文本.pdf/sample-text.pdf"
python -m document_cleaning "workshops/pdf/扫描.pdf/sample-scan.pdf" --tier advanced
```

统一 Python 接口：

```python
from document_cleaning import parse_document

result = parse_document(
    "report.pdf", engine="mineru", tier="advanced",
    output_dir="outputs", chunk_size=1200, overlap=150,
)
print(result.output_dir)
print(result.chunks[:2])
```

Notebook 界面另需 `pip install -r requirements.txt`。所有 Notebook 默认 `RUN_INFERENCE = False`，准备好环境后主动改为 `True`。音频样例需自行提供。

导入本项目不加载模型；显式调用解析函数会开始处理，上游引擎可能自动获取缺失权重。已下载模型可通过 [.env.example](.env.example) 所列环境变量指定；该文件不会自动加载。运行时、模型路径和 CPU/GPU 支持以官方说明为准。

## 输出与分块

每次解析使用独立目录 `outputs/<文件名>-<随机标识>/`：

- `document.md`：文档 Markdown；图片引擎为各页 Markdown 的索引，以保持资源路径有效。
- `document.json`：来源、引擎、内容块与分块。
- `chunks.json`：文本、来源、块编号及实际提供的页码、坐标或时间信息。
- 引擎原始 JSON、页面 Markdown 与资源文件：保留结构，便于追踪和加工。

普通文本按**字符数**切分，可带重叠；表格和公式保持整块，可能超过字符预算。音频分块保留父片段的时间范围和词级记录，字符窗口边界不等于精确音频剪辑边界。没有来源页码的内容保留空值。

## 项目结构

```text
document_cleaning/          统一路由、引擎适配与分块
_extracted/                各格式的薄封装
workshops/                 10 个默认不执行推理的 Notebook 与虚构样例
requirements-*.txt         按任务拆分的可选依赖
docs/ENGINES.md             官方资料与选型边界
docs/SAMPLES.md             样例来源说明
scripts/generate_samples.py 虚构样例生成工具
```

现在以 `document_cleaning/` 为实现来源，Notebook 直接导入。`_extracted` 提供 `extract()` 和 `extract_and_chunk()`；旧 Notebook 专用函数签名已替换。旧后端测试已移除，GitHub 工作流仅保留手动触发的静态检查。

## 能力边界与样例

目前没有视频画面理解、视频时间轴解析、邮件附件递归解析或向量数据库接入，也不保证自动去除邮件签名、回复链或网页导航。旧版 `.doc` / `.ppt` 需先转换。Office 内嵌图片默认保留结构或题注，不自动逐张做视觉描述。

公开样例是程序生成的虚构资料。生成依赖单独放在 `requirements-samples.txt`，与解析引擎分开。第三方历史素材保留在本地忽略目录，见 [样例说明](docs/SAMPLES.md)。

尚未做跨引擎质量评测、硬件兼容性或依赖组合验证。本项目没有把官方基准成绩当成本仓库实测成绩。
