import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag


def clean_text(text: str) -> str:
    '''Tab 转空格，合并连续空白，去首尾空白。'''
    text = text.replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# 解析时直接删掉的噪音标签——不含正文
_NOISE_TAGS = {
    'script', 'style', 'nav', 'footer', 'aside',
    'noscript', 'iframe', 'button', 'select', 'input', 'form',
}

# HTML 原生标题标签（比 DOCX 好判断——标签名直接告诉你）
_HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}


@dataclass
class Element:
    '''解析出的一个 HTML 文档元素。'''
    index:     int
    category:  str   # Title / Text / ListItem / Table / Image
    text:      str   # 清洗后文字；Image 格式为 "[图片: src | 章节: xxx]"
    image_src: str = ''  # 仅 Image 有值，存原始 src（可能是相对路径或 URL）

def _table_to_text(table_tag: Tag) -> str:
    '''把 <table> 转为纯文本，每行用 " | " 分隔列。'''
    rows = []
    for tr in table_tag.find_all('tr'):
        cells = [clean_text(td.get_text()) for td in tr.find_all(['td', 'th'])]
        if any(cells):
            rows.append(' | '.join(cells))
    return '\n'.join(rows)


def _is_style_heading(tag: Tag) -> bool:
    '''
    脏 HTML 兜底：对普通 <p> 判断是否是用 CSS 伪装的标题。
    触发条件（满足其一）：
    - class 名含 title / heading / subtitle
    - inline style font-size >= 14pt 或 >= 18px
    排除条件：文本 >= 80 字 或 以标点结尾（那是正文）
    '''
    text = clean_text(tag.get_text())
    if not text or len(text) >= 80:
        return False
    if re.search(r'[.。!！?？;；,，]$', text):
        return False

    # CSS class 信号（如 example.html 的 Subtitle / Title）
    classes = ' '.join(tag.get('class', [])).lower()
    if re.search(r'title|heading|subtitle', classes):
        return True

    # inline style 字号 >= 14pt 或 >= 18px
    style = tag.get('style', '')
    m = re.search(r'font-size:\s*([\d.]+)(pt|px)', style)
    if m:
        size, unit = float(m.group(1)), m.group(2)
        if (unit == 'pt' and size >= 14) or (unit == 'px' and size >= 18):
            return True

    return False


def extract(html_path: Path) -> tuple[list[Element], list[Element]]:
    '''
    解析 HTML，返回 (正文元素列表, 元信息元素列表)。

    正文类型：Title / Text / ListItem / Table / Image
    元信息：<title> 标签内容（DocTitle）

    处理顺序
    --------
    1. 删噪音标签（script / style / nav / footer / form 等）
    2. 按文档顺序遍历 h1-h6 / p / li / table / img
    3. table 内的 p / li 跳过，避免重复
    4. <p> 额外过 _is_style_heading() 兜底（脏 HTML 用）
    5. 用 current_section 追踪最新标题，写入 Image 的章节信息
    '''
    html_text = html_path.read_text(encoding='utf-8', errors='replace')
    soup = BeautifulSoup(html_text, 'html.parser')

    # 抽 <title> 作为元信息
    meta: list[Element] = []
    title_tag = soup.find('title')
    if title_tag:
        t = clean_text(title_tag.get_text())
        if t:
            meta.append(Element(index=0, category='DocTitle', text=t))

    # 删噪音标签（改变 soup 本身，后续遍历不会再碰到它们）
    for noise in soup.find_all(_NOISE_TAGS):
        noise.decompose()

    body = soup.find('body') or soup
    elements: list[Element] = []
    current_section = ''  # 追踪最近一个标题，给图片记章节用

    _WALK_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'table', 'img']

    for tag in body.find_all(_WALK_TAGS):

        # table 内的 p / li 由 table 整体处理，跳过
        if tag.name in ('p', 'li') and tag.find_parent('table'):
            continue

        # --- 标题 ---
        if tag.name in _HEADING_TAGS:
            t = clean_text(tag.get_text())
            if t:
                current_section = t
                elements.append(Element(index=len(elements), category='Title', text=t))

        # --- 段落 ---
        elif tag.name == 'p':
            t = clean_text(tag.get_text())
            if not t:
                continue
            # 先尝试脏 HTML 兜底，判断是否是伪装成段落的标题
            cat = 'Title' if _is_style_heading(tag) else 'Text'
            if cat == 'Title':
                current_section = t
            elements.append(Element(index=len(elements), category=cat, text=t))

        # --- 列表项 ---
        elif tag.name == 'li':
            # 只取本层文字，忽略嵌套 ul/ol（避免子项文字重复出现）
            parts = []
            for child in tag.children:
                if isinstance(child, NavigableString):
                    parts.append(str(child))
                elif isinstance(child, Tag) and child.name not in ('ul', 'ol', 'li'):
                    parts.append(child.get_text())
            t = clean_text(' '.join(parts))
            if t:
                elements.append(Element(index=len(elements), category='ListItem', text='• ' + t))

        # --- 表格 ---
        elif tag.name == 'table':
            # 跳过嵌套在其他 table 里的 table（布局表格常见）
            if tag.find_parent('table'):
                continue
            t = _table_to_text(tag)
            if t.strip():
                elements.append(Element(index=len(elements), category='Table', text=t))

        # --- 图片 ---
        elif tag.name == 'img':
            src = tag.get('src', '') or tag.get('data-src', '')
            alt = clean_text(tag.get('alt', ''))
            label = alt if alt else (src if src else '无src')
            elements.append(Element(
                index=len(elements),
                category='Image',
                text=f'[图片: {label} | 章节: {current_section}]',
                image_src=src,
            ))

    return elements, meta

# 在 article-zh.html 上跑一下，看提取出的元素列表
from collections import Counter

html_path = Path('.html\example-10k-1p.html')

body_els, meta_els = extract(html_path)

print(f'文件: {html_path.name}')
print(f'正文元素: {len(body_els)} 个，类型分布: {dict(Counter(e.category for e in body_els))}')
print(f'元信息: {meta_els}')
print(f'总字符: {sum(len(e.text) for e in body_els)}')
print()
print('=' * 60)
for e in body_els:
    print(f'[{e.index:2d}] ({e.category:8s}) {e.text[:80]}')

@dataclass
class RagChunk:
    '''RAG 用的一块数据，带元信息方便检索。'''
    text:        str
    source_file: str
    section:     str
    chunk_index: int
    char_count:  int = field(init=False)

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
    基于元素列表做 RAG 分块（逻辑与 DOCX 版相同）。

    - Title → flush 缓冲区，section 更新
    - Table / Image → flush，单独成块
    - Text / ListItem → 累积；满 chunk_size 切出一块，保留 overlap 字
    '''
    chunks: list[RagChunk] = []
    current_section = 'General'
    buffer = ''

    def add_chunk(text: str):
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
        if el.category == 'Title':
            flush()
            current_section = el.text
        elif el.category == 'Table':
            flush()
            add_chunk(el.text)
        elif el.category == 'Image':
            flush()
            if len(el.text.strip()) >= min_chunk_size:
                chunks.append(RagChunk(
                    text=el.text.strip(),
                    source_file=source_file,
                    section=current_section,
                    chunk_index=len(chunks),
                ))
        else:  # Text / ListItem
            buffer += el.text + '\n'
            while len(buffer) >= chunk_size:
                add_chunk(buffer[:chunk_size])
                buffer = buffer[chunk_size - overlap:]
    flush()
    return chunks

rag_chunks = chunk_elements(body_els, source_file=html_path.name, chunk_size=400)

text_chunks  = [c for c in rag_chunks if not c.text.startswith('[图片:')]
image_chunks = [c for c in rag_chunks if c.text.startswith('[图片:')]

print(f'正文元素: {len(body_els)} 个 → RAG 分块: {len(rag_chunks)} 块')
print(f'  文字块: {len(text_chunks)}  图片块: {len(image_chunks)}')
print(f'总字符: {sum(c.char_count for c in rag_chunks)}')
print()

for c in rag_chunks:
    tag = '🖼' if c.text.startswith('[图片:') else '📄'
    print(f'{tag} [{c.chunk_index:2d}] section={c.section[:30]:30s} len={c.char_count:4d}')
    print(f'   {c.text[:100]}')
    print()

import base64


def resolve_image_path(html_path: Path, image_src: str) -> Path | None:
    '''
    把 HTML 里的 src 解析成本地绝对路径。
    - 相对路径 → html 文件同级目录下寻找
    - URL（http/https）→ 返回 None，需要另行下载
    '''
    if not image_src or image_src.startswith('data:'):
        return None
    if image_src.startswith(('http://', 'https://')):
        return None  # 远程图片，暂不处理
    candidate = (html_path.parent / image_src).resolve()
    return candidate if candidate.exists() else None


def caption_image(img_path: str, model_fn=None) -> str:
    '''
    生成图片文字描述（caption）。与 DOCX / PPT 版接口完全相同。

    参数
    ----
    img_path : 本地图片路径
    model_fn : 接受图片路径、返回描述字符串的函数。
               None 时返回占位符，等待接入具体模型。

    接入示例（GPT-4o）
    -----------------
        import openai
        client = openai.OpenAI()

        def gpt4o_caption(path: str) -> str:
            ext  = Path(path).suffix.lstrip('.')
            b64  = base64.b64encode(open(path, 'rb').read()).decode()
            resp = client.chat.completions.create(
                model='gpt-4o',
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'image_url',
                         'image_url': {'url': f'data:image/{ext};base64,{b64}'}},
                        {'type': 'text',
                         'text': '请用中文详细描述这张图片的内容，包括文字、结构和关键信息。'},
                    ],
                }],
                max_tokens=500,
            )
            return resp.choices[0].message.content

        caption = caption_image(img_path, model_fn=gpt4o_caption)
    '''
    if model_fn is None:
        return f'[待识别: {Path(img_path).name}]'
    return model_fn(img_path)


# 对所有图片 chunk 生成 caption，追加到 text
print('图片 caption（当前为占位符，接入模型后自动替换）：\n')
captioned_chunks = []
for chunk in rag_chunks:
    if not chunk.text.startswith('[图片:'):
        captioned_chunks.append(chunk)
        continue

    # 从对应 Element 里找 image_src
    img_el = next(
        (e for e in body_els if e.category == 'Image' and e.text == chunk.text),
        None,
    )
    local_path = resolve_image_path(html_path, img_el.image_src) if img_el else None

    if local_path:
        cap = caption_image(str(local_path))  # 接入模型时传 model_fn=xxx
    else:
        cap = '[远程图片或路径无效，需手动下载后再识别]'

    chunk.text = chunk.text + '\n' + cap
    chunk.char_count = len(chunk.text)
    captioned_chunks.append(chunk)
    print(f'  {chunk.text[:120]}')

print(f'\nCaption 完成，共 {len(captioned_chunks)} 个 chunk（含 {len(image_chunks)} 个图片 chunk）')