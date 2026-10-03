# Document Cleaning & Extraction

面向 RAG（检索增强生成）的多格式文档清洗、内容提取与分块实践。

本项目通过 Jupyter Notebook 展示不同格式文件的处理思路：识别正文、标题、表格和图片，清理格式相关噪音，再组织成带来源信息的文本块。适合学习文档预处理、比较不同格式的清洗策略，或作为知识库数据处理的起点。

项目以实战示例和策略探索为主，当前没有统一的命令行入口，也不包含向量数据库、检索服务或完整的 RAG 应用。

## 支持的场景

| 文件类型 | 主要处理策略 | Notebook |
| --- | --- | --- |
| Word / DOCX | 正文与页眉页脚分离；中英文标题启发式识别；表格独立分块；图片提取与章节关联 | [Word 清洗](workshops/word/clean-pure-text.ipynb) |
| 纯文本 PDF | 转换为 Markdown；按标题分节；表格独立成块；正文滑动窗口分块 | [纯文本 PDF](workshops/pdf/纯文本.pdf/clean-pure-text.ipynb) |
| 扫描 PDF | 通过解析库与本地 OCR 环境提取内容，再按标题、表格和正文组织分块 | [扫描 PDF](workshops/pdf/扫描.pdf/clean-scan-pdf.ipynb) |
| 图文混排 PDF | 分别提取文字和嵌入图片；尝试按页码与纵向位置合并；为图片补充描述 | [图文混排 PDF](workshops/pdf/图文混排.pdf/clean-mixed-pdf.ipynb) |
| HTML | 删除导航、脚本等噪音；识别原生标题和样式标题；处理列表、表格与图片上下文 | [HTML 清洗](workshops/html/clean-html.ipynb) |
| 邮件 / EML | 提取邮件头与正文；清理历史回复和签名；识别列表、表格并记录附件信息 | [邮件清洗](workshops/email/clean-email.ipynb) |
| PowerPoint / PPTX | 根据跨页频率识别模板文字；提取标题、正文、表格和图片；按幻灯片分块 | [PPT 清洗](workshops/ppt/clean-ppt.ipynb) |
| 图片 | 本地 OCR；结合网格线、文字量和饱和度判断内容成分；按需调用模型还原表格或描述图片 | [图片清洗](workshops/img/clean-image.ipynb) |
| CSV / TSV / XLSX | 处理 UTF-8 BOM、空工作表和表头；将表格转换为文本并保留工作表信息 | [表格清洗](workshops/xlsx/clean-data.ipynb) |
| 音频 | 使用 Whisper 转写；聚合相邻转写片段；保留开始、结束时间及片段重叠 | [音频清洗](workshops/media/clean-audio.ipynb) |

`workshops/其他格式/` 保存了一些额外格式的样例文件，目前没有对应的完整清洗流程。目录中的文件不代表这些格式都已支持，例如 `.doc`、`.msg`、EPUB 等。

## 清洗与分块思路

### 先识别结构，再组织内容

不同格式使用不同的结构信号：Word 的元素分类和编号标题、HTML 的标签与样式、PPT 的标题占位符，以及 PDF 转换后的 Markdown 标题。提取结果通常区分标题、正文、表格和图片，便于按章节组织内容。

### 按格式清理噪音

除了合并空白和去除首尾空格，还包含格式相关策略：Word 过滤页眉页脚等元信息，HTML 删除导航和脚本标签，邮件截去历史引用与签名，PPT 根据短文本的跨页出现频率识别模板噪音。

这些规则属于启发式处理，需要根据实际文档调整，可能误删有意义的重复内容，或将短正文误判为标题。

### 为表格、图片和音频保留上下文

表格通常单独成块，避免与普通正文混切；图片保留文件位置或章节信息，并可补充模型生成的描述；音频文本块保留时间戳，方便回到原始片段。

正文按字符数进行分块，部分流程保留重叠内容。这里的 `chunk_size` 通常指字符数，而非模型 token 数；表格和图片块不一定遵循正文的长度限制。

## 目录结构

```text
.
├── workshops/                 # 按格式组织的 Notebook 与样例
│   ├── word/
│   ├── pdf/
│   │   ├── 纯文本.pdf/
│   │   ├── 扫描.pdf/
│   │   └── 图文混排.pdf/
│   ├── html/
│   ├── email/
│   ├── ppt/
│   ├── img/
│   ├── xlsx/
│   ├── media/
│   └── 其他格式/
├── _extracted/                # 从 Notebook 提取的 Python 代码
├── main.py                    # 预留入口，当前为空
└── .gitignore
```

部分样例放在 `.docx/`、`.ppt/`、`.html/` 等以点开头的子目录中；若文件浏览器隐藏这些目录，可开启隐藏文件显示。

`_extracted/` 便于浏览和参考核心函数，尚未整理成可直接导入的 Python 包。部分文件保留演示代码或依赖 Notebook 中的变量，运行时应优先使用 Notebook。

## 开始使用

### 1. 创建 Python 环境

建议使用 Python 3.10 或更高版本，在项目根目录创建虚拟环境。

```bash
python -m venv .venv
```

Windows PowerShell 激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux 激活环境：

```bash
source .venv/bin/activate
```

### 2. 按需安装依赖

下列命令根据项目中的导入整理，供环境准备参考。项目尚未锁定依赖版本，各解析库的行为可能随版本变化。

先安装 Notebook 环境：

```bash
python -m pip install jupyterlab ipykernel
```

根据要运行的示例，选择安装对应依赖：

| 场景 | Python 依赖 |
| --- | --- |
| Word | `unstructured[docx]`、`python-docx`、`openai` |
| PDF | `pymupdf4llm`、`pymupdf`；图文混排示例还使用 `openai` |
| HTML、邮件 | `beautifulsoup4` |
| PPT | `python-pptx`、`openai` |
| 图片 | `opencv-python`、`numpy`、`pytesseract`、`Pillow`、`openai` |
| XLSX | `openpyxl`；CSV / TSV 的读取使用 Python 标准库 |
| 音频 | `openai-whisper` |

例如，先体验 HTML、邮件和表格处理：

```bash
python -m pip install beautifulsoup4 openpyxl
```

OCR 相关示例需要额外准备 Tesseract 和对应语言数据。图片示例默认使用 `chi_sim+eng`；代码中包含 Windows 常见安装路径，其他安装位置或系统需调整。扫描 PDF 的 OCR 行为还取决于所安装的解析库版本及环境配置。

音频转写需要 FFmpeg；首次使用 Whisper 时可能下载模型权重。部分 Word 英文标题判断依赖 `unstructured` 的词性分析，按相关库的提示准备所需资源。

### 3. 打开 Notebook

```bash
jupyter lab
```

也可以使用 VS Code 的 Jupyter 支持打开 `.ipynb` 文件，并选择刚创建的虚拟环境作为内核。

选择一个格式目录，检查 Notebook 中的样例路径，再按顺序运行单元格。样例路径通常相对于 Notebook 所在目录；如果出现找不到文件的提示，请检查内核的工作目录，或将输入路径改成实际文件路径。

建议从 HTML、邮件或 CSV / XLSX 示例开始，再尝试 PDF、图片和音频流程。

## 图片描述与模型配置

Word、PPT、图文混排 PDF 及图片示例中包含阿里云百炼的图片处理调用，使用 OpenAI 兼容客户端，并从环境变量读取密钥：

```powershell
# Windows PowerShell：仅为当前会话设置
$env:DASHSCOPE_API_KEY = "你的 API Key"
```

```bash
# macOS / Linux：仅为当前会话设置
export DASHSCOPE_API_KEY="你的 API Key"
```

请在设置环境变量的同一会话中启动 Jupyter；如果内核已经启动，需重新启动相关进程使配置生效。代码没有自动加载 `.env` 的逻辑。

模型名称通过各示例中的 `_CAPTION_MODEL` 设置，可按账号可用模型调整。图片描述和表格还原会将图片发送到外部服务，并可能产生调用费用。

- 图片流程可通过 `with_api=False` 跳过模型调用，仅保留本地检测与符合条件的 OCR 输出。
- HTML 的 `caption_image()` 默认返回占位文本，需要传入 `model_fn` 才会执行实际识别。
- Word、PPT 和图文混排 PDF 的部分处理步骤直接调用模型，运行这些步骤前需配置密钥，或自行跳过图片描述部分。

不要将真实密钥写进代码或 Notebook 输出后提交。仓库的 `.gitignore` 已忽略 `.env` 和 `.env.*` 文件。

## 输出形式与当前边界

各示例使用 `Element`、`RagChunk` 等数据类组织结果。文本块通常包含 `text`、`source_file`、`section`、`chunk_index` 和 `char_count`；根据格式，还可能包含页码、幻灯片编号、图片路径或音频时间戳。这些结构尚未统一为固定接口。

当前示例主要在 Notebook 内展示结果，尚未提供统一的批量处理与导出流程。使用时还需注意：

- PDF 中跨页文本的页码归属，以及复杂多栏布局的图文顺序，仍有改进空间。
- 表格转文本并不完整保留原始版式；合并单元格、超大表格等场景需要进一步处理。
- 正文主要按字符长度切分，未统一处理句子边界、标题层级或模型 token 预算。
- 调整滑动窗口参数时，应保证 `chunk_size > 0` 且 `0 <= overlap < chunk_size`。
- 模型生成的图片描述和表格内容可能存在遗漏，需要结合原文判断。

仓库包含多种样例及部分提取出的图片。样例用于展示处理流程，其来源与使用范围需分别核对；本 README 不为第三方样例声明统一授权。
