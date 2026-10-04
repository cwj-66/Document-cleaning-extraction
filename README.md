# Document Cleaning & Extraction

**面向知识库的多格式文档清洗、内容提取与分块实践。**

不同格式的问题并不相同：网页有导航和脚本，邮件有引用和签名，Word 与 PPT 有章节、表格和图片，扫描 PDF 需要 OCR，音频则需要先转写。本仓库用 **10 个 Jupyter Notebook** 展示这些处理路径，将内容组织成保留来源信息的文本块，供后续知识检索使用。

Notebook 是主要入口，`_extracted/` 提供对应的 Python 函数导出。仓库没有统一解析服务、向量数据库或问答应用，也没有视频解析、MinerU 或 Docling 集成。

## 处理能力

| 场景 | 实际采用的方法 | 输出与边界 | 示例 |
| --- | --- | --- | --- |
| Word / DOCX | `unstructured` 提取元素；`python-docx` 与 ZIP 提取图片；启发式补充中英文标题识别 | 按章节组织正文，表格与图片独立分块；图片与正文的全局顺序未统一 | [Word](workshops/word/clean-pure-text.ipynb) |
| 有文字层的 PDF | `pymupdf4llm` 转 Markdown，按标题、表格与字符窗口分块 | 保留页码；复杂多栏与标题识别需核对 | [文本 PDF](workshops/pdf/纯文本.pdf/clean-pure-text.ipynb) |
| 扫描 PDF | 无文本层页面显式调用 PyMuPDF + Tesseract OCR；已有文字的页面转 Markdown | 保留页码；OCR 纯文本不保证还原表格、标题与阅读顺序 | [扫描 PDF](workshops/pdf/扫描.pdf/clean-scan-pdf.ipynb) |
| 图文混排 PDF | `pymupdf4llm` 提取文字，PyMuPDF 提取嵌入图片；按页码和估算纵向位置合并 | 图片可选模型描述；文字块与版面区域并非精确匹配 | [混排 PDF](workshops/pdf/图文混排.pdf/clean-mixed-pdf.ipynb) |
| HTML | BeautifulSoup 去除导航、脚本等标签，识别标题、列表、表格与图片上下文 | 本地文件解析；远程图片不自动下载，图片描述默认为占位符 | [HTML](workshops/html/clean-html.ipynb) |
| 邮件 / EML | 标准库解析 MIME，BeautifulSoup 处理 HTML 正文，规则清理回复与签名 | 提取邮件头和正文；附件只记录名称与类型，不解析附件内容 | [邮件](workshops/email/clean-email.ipynb) |
| PowerPoint / PPTX | `python-pptx` 提取文字、表格和图片，按短文本跨页频率识别模板噪音 | 正文按幻灯片组织，过长时分块；表格、图片独立成块 | [PPT](workshops/ppt/clean-ppt.ipynb) |
| 图片 | Tesseract OCR；OpenCV 网格线与颜色启发式检测；可选模型描述或表格还原 | 每张图片输出一块；无线框表格、低清扫描可能漏判 | [图片](workshops/img/clean-image.ipynb) |
| CSV / TSV / XLSX | 标准库 `csv` / `openpyxl` 读取，处理 BOM、空工作表及表头 | 保留行列文本和工作表名称；整表成块，超大表格需另行拆分 | [表格](workshops/xlsx/clean-data.ipynb) |
| 音频 | 本地 Whisper 转写，按 segment 聚合，保留重叠与时间戳 | 保留起止时间；需自行提供有权使用的音频，转写效果依赖模型与音质 | [音频](workshops/media/clean-audio.ipynb) |

支持文件由各 Notebook 分别处理，没有自动格式路由。`.doc`、`.ppt`、`.msg`、EPUB 和视频不在当前实现范围内。

## 快速开始：先运行一个轻量示例

建议使用 Python 3.11 或更高版本。下面从不需要 OCR、模型密钥或模型权重的 HTML 示例开始。

```bash
git clone https://github.com/cwj-66/Document-cleaning-extraction.git
cd Document-cleaning-extraction
python -m venv .venv
```

激活虚拟环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

安装基础依赖、生成虚构样例并启动 Notebook：

```bash
python -m pip install -r requirements.txt
python scripts/generate_samples.py
jupyter lab
```

打开 [HTML Notebook](workshops/html/clean-html.ipynb)，选择虚拟环境内核，从上到下运行。邮件和 CSV / TSV 示例也可以用同一环境运行。

样例路径相对于 **Notebook 所在目录**。在 VS Code 或其他环境中如遇找不到文件，先用 `Path.cwd()` 检查工作目录，再切换到 Notebook 目录或改成实际输入路径。部分样例目录以点开头，例如 `.docx/`、`.html/`、`.ppt/`。

## 按场景准备环境

只安装要运行的场景，不必一次装全。

| 场景 | 安装命令 | 额外准备 |
| --- | --- | --- |
| HTML、EML、CSV / TSV / XLSX | `python -m pip install -r requirements.txt` | XLSX 可用自己的文件，或通过完整样例命令生成 |
| Word、PPT、PDF | `python -m pip install -r requirements-documents.txt` | 扫描 PDF 需要 Tesseract 与语言数据；Word 英文词性判断可能需要 NLTK 资源 |
| 图片 | `python -m pip install -r requirements-image.txt` | Tesseract，默认 `chi_sim+eng` 语言数据 |
| 音频 | `python -m pip install -r requirements-audio.txt` | FFmpeg；首次使用 Whisper 会下载模型权重 |

`requirements-documents.txt` 将 PyMuPDF 与 pymupdf4llm 固定为本次检查环境中的同一版本，避免两者不兼容。其他依赖文件给出安装范围，不是所有平台的完整锁文件。

安装文档依赖后生成 Word、PPT、XLSX、图片和三类 PDF 的虚构样例：

```bash
python scripts/generate_samples.py --documents
```

脚本只在目标文件不存在时生成；明确需要重建时加 `--overwrite`。音频不生成：请在 `workshops/media/` 放入自己有权使用的 `sample.wav`，或修改 Notebook 的 `audio_path`。批量演示的语言判断只是按文件名猜测，可自行指定 `zh` / `en`，或用 `None` 自动检测。

### OCR 配置

Tesseract 是独立程序，安装 `pytesseract` 并不会安装它。请安装所需语言数据：扫描 PDF 默认 `eng`，图片默认 `chi_sim+eng`。扫描 PDF 可通过 `ocr_language="chi_sim+eng"` 指定语言。

Notebook 会尝试 Windows 常见安装位置，已有环境设置优先。例如：

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:TESSDATA_PREFIX = "C:\Program Files\Tesseract-OCR\tessdata"
```

`TESSERACT_CMD` 用于图片示例的 pytesseract；扫描 PDF 使用 PyMuPDF 的 OCR 接口，并通过 `TESSDATA_PREFIX` 查找语言数据。其他系统可将 Tesseract 加入 `PATH` 并设置实际的语言数据目录。

## 可选：图片描述与表格还原

**默认只运行本地处理，不调用外部模型。** Word、PPT、图文混排 PDF 和图片的相关主函数都有 `with_api=False` 参数；显式传入 `with_api=True` 才会请求模型。

示例使用 OpenAI 兼容客户端连接阿里云百炼，通过环境变量读取配置：

```powershell
$env:DASHSCOPE_API_KEY = "你的 API Key"
$env:CAPTION_MODEL = "你的账号可用且支持图片输入的模型名称"
```

```bash
export DASHSCOPE_API_KEY="你的 API Key"
export CAPTION_MODEL="你的账号可用且支持图片输入的模型名称"
```

请在同一会话中启动 Jupyter。`.env.example` 仅展示变量名称，代码不会自动加载 `.env`；默认模型名沿用 `qwen3.6-flash`，实际可用性以账号为准。开启模型调用会发送图片到外部服务并可能产生费用。

HTML 的 `caption_image(path, model_fn=None)` 是可插拔接口，未提供 `model_fn` 时返回占位文本。模型生成内容需对照原图核验。

## 用 Python 函数处理自己的文件

导出文件只包含定义，导入时不会读取样例、打印结果或启动模型。各格式接口仍有区别；例如在仓库根目录运行 HTML：

```python
from dataclasses import asdict
from pathlib import Path
import json

from _extracted.html import extract, chunk_elements

source = Path("workshops/html/.html/sample.html")
elements, metadata = extract(source)
chunks = chunk_elements(elements, source_file=source.name, chunk_size=400, overlap=80)

print(json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2))
```

常见字段为 `text`、`source_file`、`section`、`chunk_index`、`char_count`。PDF 和图片可能增加 `page`、`image_path`，PPT 增加 `slide_num`，音频增加 `start_time` / `end_time`。这些数据类并非统一接口，接入其他系统时需自行映射。

正文通常按**字符数**切分，而非 token 数；表格、图片与完整音频 segment 可能超出正文长度预算。窗口参数要求 `chunk_size > 0`、`0 <= overlap < chunk_size`。音频的 `overlap_segs` 指 segment 数量。

## 目录与维护

```text
.
├── workshops/                 # 10 个 Notebook，按格式组织
│   ├── word/  html/  email/  ppt/
│   ├── pdf/                   # 文本、扫描、图文混排
│   └── img/  xlsx/  media/
├── _extracted/                # 自动导出的函数；不要单独修改
├── scripts/
│   ├── generate_samples.py    # 生成虚构样例
│   └── export_notebooks.py    # 同步 Notebook 定义到 Python
├── tests/                     # 本地回归检查
├── docs/SAMPLES.md            # 样例来源与公开版处理说明
├── requirements*.txt          # 分场景依赖
└── .env.example
```

修改 Notebook 后更新导出，并检查两者是否一致：

```bash
python scripts/export_notebooks.py
python scripts/export_notebooks.py --check
python -m unittest discover -s tests -v
```

基础测试使用 `requirements.txt`，不调用外部模型。PDF、Word、PPT 的检查需要文档依赖；未安装时会跳过对应测试。OCR 和真实音频转写另需系统依赖与输入文件，不能仅凭基础测试通过认定所有场景已验证。

## 当前限制

- 标题识别、模板去噪、邮件引用清理和图片成分判断使用启发式规则，可能误删或漏判，需要用实际输入调整。
- PDF 分块在页边界结束缓冲区，便于保留页码，但不合并跨页表格。图文混排的纵向排序是近似值，多栏和复杂版面仍可能错序。
- OCR 错字、低分辨率、中文方言与背景噪声会影响提取和转写；未提供全面准确率测评。
- Word 图片按章节关联后参与分块，不保证恢复全部图文交错顺序；PPT 不处理嵌入对象的所有类型。
- XLSX 使用 `data_only=True` 读取已有公式缓存，不计算公式；缺少缓存的公式单元格可能为空。
- 没有统一批量路由、稳定公共 API 或完整 RAG 服务。

## 样例与公开范围

公开版样例由 `scripts/generate_samples.py` 生成，内容均为虚构演示。原有第三方素材在本次整理时移至本地忽略目录，不再随当前版本分发；详情见 [样例说明](docs/SAMPLES.md)。历史版本可能仍包含旧素材，本次未改写 Git 历史。

本仓库未指定统一代码许可证；公开可阅读不等同于授予任意使用许可。第三方库的许可与使用条件以各自项目为准。
