import base64
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz
import pymupdf4llm
from openai import OpenAI

_HEADING_RE = re.compile(r'^(#{1,3})\s+(.+)', re.MULTILINE)
_CAPTION_MODEL = 'qwen3.6-flash'


@dataclass
class RagChunk:
    '''RAG 分块。'''
    text: str
    source_file: str
    section: str
    page: int
    chunk_index: int
    image_path: str = ''
    y0: float = 0.0        # 页面上的垂直位置，用于排序
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)


def _is_table_line(line: str) -> bool:
    s = line.strip()
    return s.startswith('|') and s.endswith('|')


def extract_images(pdf_path: Path) -> list[dict]:
    '''抽嵌入图，保存到 {stem}_images/，返回含 page/y0/fname/image_path 的列表。'''
    img_dir = pdf_path.parent / f'{pdf_path.stem}_images'
    img_dir.mkdir(exist_ok=True)
    doc = fitz.open(str(pdf_path))
    images: list[dict] = []

    for page_num, page in enumerate(doc, start=1):
        seen: set[int] = set()
        for i, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            base = doc.extract_image(xref)
            if not base or not base.get('image'):
                continue
            ext = base.get('ext') or 'png'
            fname = f'img_p{page_num}_{i}.{ext}'
            out = img_dir / fname
            out.write_bytes(base['image'])
            rects = page.get_image_rects(xref)
            images.append({
                'page': page_num,
                'y0': rects[0].y0 if rects else float(i * 100),
                'fname': fname,
                'image_path': str(out),
            })
    doc.close()
    return images


def extract_and_chunk(
    pdf_path: Path,
    chunk_size: int = 500,
    overlap: int = 100,
    min_chunk_size: int = 20,
) -> list[RagChunk]:
    '''
    文字分块 + 图片分块，按 (page, y0) 排序合并。

    - 文字：pymupdf4llm → 逐行处理，生成文字块；再用 PyMuPDF 拿到每块的真实 y0
    - 图片：PyMuPDF 抽图，本身就有 y0
    - 合并：两者一起按 y0 排序，保持页面阅读顺序
    '''
    # --- 文字分块 ---
    pages_md = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    lines, line_pages = [], []
    for page in pages_md:
        p = page['metadata']['page_number']
        for line in page['text'].splitlines():
            lines.append(line)
            line_pages.append(p)

    text_chunks: list[RagChunk] = []
    page_sections: dict[int, str] = {}
    section, cur_page, buf, table = 'General', 1, '', []
    # 先用页内顺序（0, 1, 2...）作为临时 y0，后面用 PyMuPDF 替换成真实坐标
    page_chunk_counter: dict[int, int] = {}

    def add_text(text: str, page: int):
        text = text.strip()
        if len(text) >= min_chunk_size:
            idx = page_chunk_counter.get(page, 0)
            page_chunk_counter[page] = idx + 1
            text_chunks.append(RagChunk(
                text=text, source_file=pdf_path.name,
                section=section, page=page, chunk_index=0, y0=float(idx),
            ))

    def flush_text():
        nonlocal buf
        while len(buf) >= chunk_size:
            add_text(buf[:chunk_size], cur_page)
            buf = buf[chunk_size - overlap:]
        add_text(buf, cur_page)
        buf = ''

    def flush_table():
        nonlocal table
        if table:
            add_text('\n'.join(table), cur_page)
            table = []

    for line, page_num in zip(lines, line_pages):
        cur_page = page_num
        page_sections[page_num] = section
        m = _HEADING_RE.match(line)
        if m:
            flush_text(); flush_table()
            section = re.sub(r'\*+', '', m.group(2)).strip()
            page_sections[page_num] = section
        elif _is_table_line(line):
            if buf.strip():
                flush_text()
            table.append(line.strip())
        else:
            flush_table()
            if line.strip():
                buf += line + ' '
    flush_table(); flush_text()

    # --- 用 PyMuPDF 给文字块配真实 y0 ---
    # pymupdf4llm 按从上到下处理，所以第 k 个文字块对应第 k 个文本区域的 y0
    doc = fitz.open(str(pdf_path))
    for page_num, page in enumerate(doc, start=1):
        block_y0s = sorted(
            b['bbox'][1]
            for b in page.get_text('dict')['blocks']
            if b['type'] == 0
        )
        page_tc = [c for c in text_chunks if c.page == page_num]
        for k, c in enumerate(page_tc):
            # 超出 block 数量时用大数，保证排在已知块后面
            c.y0 = block_y0s[k] if k < len(block_y0s) else float(k * 1000)
    doc.close()

    # --- 图片分块（本身有真实 y0）---
    image_chunks: list[RagChunk] = []
    for img in extract_images(pdf_path):
        sec = page_sections.get(img['page'], 'General')
        image_chunks.append(RagChunk(
            text=f"[图片: {img['fname']} | 页: {img['page']} | section: {sec}]",
            source_file=pdf_path.name, section=sec,
            page=img['page'], chunk_index=0,
            image_path=img['image_path'], y0=img['y0'],
        ))

    # --- 按 (page, y0) 排序合并 ---
    merged = text_chunks + image_chunks
    merged.sort(key=lambda c: (c.page, c.y0))
    for i, c in enumerate(merged):
        c.chunk_index = i
    return add_captions(merged)


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


def add_captions(chunks: list[RagChunk]) -> list[RagChunk]:
    '''给图片块追加 caption 描述。'''
    out: list[RagChunk] = []
    for c in chunks:
        if not c.image_path:
            out.append(c)
            continue
        cap = caption_image(c.image_path)
        out.append(RagChunk(
            text=c.text + f'\n描述: {cap}',
            source_file=c.source_file, section=c.section,
            page=c.page, chunk_index=c.chunk_index,
            image_path=c.image_path, y0=c.y0,
        ))
    return out

pdf_path = Path('insider-threat-101-factsheet.pdf')
chunks = extract_and_chunk(pdf_path)

n_img = sum(1 for c in chunks if c.image_path)
print(f'文件: {pdf_path.name}  分块: {len(chunks)}（图片 {n_img}）')
print('=' * 60)
for c in chunks:
    tag = '[图]' if c.image_path else '   '
    print(f'{tag} [{c.chunk_index}] p.{c.page} y0={c.y0:6.1f}  section={c.section}  len={c.char_count}')
    print('-' * 60)
    print(c.text)
    print()