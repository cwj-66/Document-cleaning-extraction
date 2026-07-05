import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document as _Docx
from docx.oxml.ns import qn
from unstructured.partition.docx import partition_docx

# drawingML 和 relationship 命名空间
_NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def clean_text(text: str) -> str:
    '''Tab 转空格，合并连续空白，去首尾空白。'''
    text = text.replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# 元信息类型：页眉、页脚、分页符，不进正文
META_TYPES = {'Header', 'Footer', 'PageBreak'}


@dataclass
class Element:
    '''解析出的一个文档元素。'''
    index: int
    category: str   # Title / Text / NarrativeText / Table / Image
    text: str       # 清洗后的文字；Image 格式为 "[图片: fname | 章节: xxx]"
    image_path: str = ''  # 仅 Image 类型有值，指向本地图片文件路径


def extract(docx_path: Path) -> tuple[list[Element], list[Element]]:
    '''用 unstructured 解析 docx，返回 (正文元素, 元信息元素)。'''
    body, meta = [], []
    for el in partition_docx(str(docx_path)):
        text = clean_text(str(el))
        if not text:
            continue
        cat = type(el).__name__
        item = Element(index=len(body) + len(meta), category=cat, text=text)
        (meta if cat in META_TYPES else body).append(item)
    return body, meta


def extract_images(docx_path: Path) -> list[Element]:
    '''
    从 docx 抽取图片，返回 Image 类型的 Element 列表。

    - 图片文件保存到 {docx_stem}_images/ 目录
    - 用 python-docx 遍历段落，记录每张图片所属的 Heading 章节
    - text 格式：[图片: 文件名 | 章节: 所在标题]
    '''
    img_dir = docx_path.parent / f'{docx_path.stem}_images'
    img_dir.mkdir(exist_ok=True)

    # 解析 word/_rels/document.xml.rels：rId → 图片文件名
    rid_to_file: dict[str, str] = {}
    with zipfile.ZipFile(docx_path) as z:
        rels_xml = z.read('word/_rels/document.xml.rels').decode('utf-8')
        for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="media/([^"]+)"', rels_xml):
            rid_to_file[m.group(1)] = m.group(2)
        # 把所有媒体文件写到本地
        for name in z.namelist():
            if name.startswith('word/media/'):
                fname = name.split('/')[-1]
                (img_dir / fname).write_bytes(z.read(name))

    doc = _Docx(str(docx_path))
    elements: list[Element] = []
    current_section = 'General'

    for p in doc.paragraphs:
        # 跟踪当前章节（Heading 样式）
        sty = p.style.name if p.style else ''
        if 'Heading' in sty and p.text.strip():
            current_section = clean_text(p.text)

        # 找段落里的每个 drawing → blip → rId → 文件名
        for d in p._element.findall('.//' + qn('w:drawing')):
            for blip in d.findall(f'.//{{{_NS_A}}}blip'):
                rid = blip.get(f'{{{_NS_R}}}embed')
                if rid and rid in rid_to_file:
                    fname = rid_to_file[rid]
                    elements.append(Element(
                        index=len(elements),
                        category='Image',
                        text=f'[图片: {fname} | 章节: {current_section}]',
                        image_path=str(img_dir / fname),
                    ))

    return elements

import base64
import os

from openai import OpenAI

_CAPTION_MODEL = 'qwen3.6-flash'


def caption_image(img_path: str) -> str:
    '''调百炼多模态模型生成图片描述。'''
    client = OpenAI(
        api_key=os.environ['DASHSCOPE_API_KEY'],
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )
    ext = Path(img_path).suffix.lstrip('.') or 'jpeg'
    b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
    resp = client.chat.completions.create(
        model=_CAPTION_MODEL,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:image/{ext};base64,{b64}'}},
                {'type': 'text', 'text': '请用中文描述这张图片的内容，包括文字和结构。'},
            ],
        }],
    )
    return resp.choices[0].message.content


# 中文编号前缀：一、 / 第二章 / 1.1 / （一） 等
_CN_HEADING_RE = re.compile(
    r'^(?:[一二三四五六七八九十百]+[、.]'   # 一、二、
    r'|第[一二三四五六七八九十\d]+[章节条]'  # 第一章
    r'|\d+(?:\.\d+)*[.\s]'                  # 1. / 1.1 / 1.1.2
    r'|（[一二三四五六七八九十\d]+）'        # （一）
    r')'
)
# 英文编号前缀：A. / B. / Chapter 1 / ITEM 1A
_EN_HEADING_RE = re.compile(
    r'^(?:[A-Z]\.\s|Chapter\s+\d|CHAPTER\s+\d|Item\s+\d|ITEM\s+\d)',
    re.IGNORECASE,
)
# 结尾标点：正文段落几乎都有
_END_PUNCT_RE = re.compile(r'[.。!！?？;；,，:：]$')
# 判断是否含中文字符
_HAS_CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def is_heading(text: str) -> bool:
    '''
    对 unstructured 返回的 Text 元素做启发式标题判断。

    中文：命中编号前缀即认定（强信号）。
    英文：长度<80 + 无结尾标点 + 满足「编号前缀 / 全大写 / 无动词」之一。
    '''
    # 通用前置：太长或以标点结尾 → 肯定是正文
    if len(text) >= 80 or _END_PUNCT_RE.search(text):
        return False

    # 中文/中英混合：先看英文字母编号（A. B. Chapter），再看中文编号
    # 修复：原来含中文就只查中文正则，导致「A. 目的」这类被漏判
    if _HAS_CJK_RE.search(text):
        if _EN_HEADING_RE.match(text):      # A. / B. / Chapter 等
            return True
        return bool(_CN_HEADING_RE.match(text))

    # 纯英文：多信号叠加，至少一个强信号
    if _EN_HEADING_RE.match(text):          # 有编号前缀
        return True
    if text.isupper():                       # 全大写（如 CHAPTER 1）
        return True
    # 无动词（借用 unstructured 的 POS 判断）
    try:
        from unstructured.partition.text_type import contains_verb
        if not contains_verb(text):
            return True
    except ImportError:
        pass

    return False


@dataclass
class RagChunk:
    '''RAG 用的一块数据，带元信息方便检索。'''
    text: str
    source_file: str
    section: str
    chunk_index: int
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)


def chunk_elements(
    elements: list[Element],
    source_file: str,
    chunk_size: int = 400,
    overlap: int = 80,
    min_chunk_size: int = 10,
) -> list[RagChunk]:
    '''
    基于 unstructured 分类 + 启发式标题检测做 RAG 分块（滑动窗口）。

    - Title 或 Text 命中 is_heading() → section 标题，flush 缓冲区
    - Table → flush，表格单独成块
    - 其余正文 → 累积；满 chunk_size 切出一块，保留 overlap 字继续拼接
    '''
    chunks: list[RagChunk] = []
    current_section = 'General'
    buffer = ''

    def add_chunk(text: str):
        # 过滤过短噪音块（如夹在两个标题之间的「简介」）
        if len(text.strip()) >= min_chunk_size:
            chunks.append(RagChunk(
                text=text.strip(),
                source_file=source_file,
                section=current_section,
                chunk_index=len(chunks),
            ))

    def flush():
        nonlocal buffer
        add_chunk(buffer)
        buffer = ''

    for el in elements:
        # Title（Word Heading 样式）；或正文元素命中启发式 → 当标题
        # 修复：unstructured 对中文的 Text/NarrativeText 区分不可靠，两者都交给 is_heading 判断
        if el.category == 'Title' or (el.category in ('Text', 'NarrativeText') and is_heading(el.text)):
            flush()
            current_section = el.text
        elif el.category == 'Table':
            flush()
            add_chunk(el.text)
        elif el.category == 'Image':
            flush()
            # 从 text 里取图片所属章节（优先用图片自带的 section，比当前 buffer 的 section 更准确）
            m = re.search(r'章节: (.+?)\]', el.text)
            img_section = m.group(1) if m else current_section
            if len(el.text.strip()) >= min_chunk_size:
                text = el.text.strip()
                if el.image_path:
                    text += f'\n描述: {caption_image(el.image_path)}'
                chunks.append(RagChunk(
                    text=text,
                    source_file=source_file,
                    section=img_section,
                    chunk_index=len(chunks),
                ))
        else:
            buffer += el.text + '\n'
            while len(buffer) >= chunk_size:
                add_chunk(buffer[:chunk_size])
                buffer = buffer[chunk_size - overlap:]
    flush()
    return chunks

# 合并文字/表格元素 + 图片元素，一起送入分块
all_elements = body + images

rag_chunks = chunk_elements(all_elements, source_file=docx_path.name, chunk_size=400, overlap=80)

print(f'文字/表格元素: {len(body)} 个 + 图片元素: {len(images)} 个 → RAG 分块: {len(rag_chunks)} 块')
print(f'总字符: {sum(c.char_count for c in rag_chunks)}')
print('=' * 60)
for c in rag_chunks:
    preview = c.text[:70] + '...' if len(c.text) > 70 else c.text
    tag = '[图]' if c.text.startswith('[图片:') else '   '
    print(f'\n{tag} [{c.chunk_index:2d}] section={c.section[:25]:25s} len={c.char_count:4d}')
    print(f'    {preview}')