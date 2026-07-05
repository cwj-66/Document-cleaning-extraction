import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf4llm

# Windows：Tesseract 的语言数据路径（装完通常在这里）
# pymupdf4llm 通过这个环境变量找 eng.traineddata
_TESSDATA = Path(r'C:\Program Files\Tesseract-OCR\tessdata')
if _TESSDATA.exists():
    os.environ['TESSDATA_PREFIX'] = str(_TESSDATA)


# Markdown 标题行：# / ## / ### 开头
_HEADING_RE = re.compile(r'^(#{1,3})\s+(.+)', re.MULTILINE)


@dataclass
class RagChunk:
    '''RAG 用的一块数据，带元信息方便检索。'''
    text:        str
    source_file: str
    section:     str
    page:        int
    chunk_index: int
    char_count:  int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)

def _is_table_line(line: str) -> bool:
    '''Markdown 表格行：以 | 开头且以 | 结尾。'''
    s = line.strip()
    return s.startswith('|') and s.endswith('|')


def extract_and_chunk(
    pdf_path: Path,
    chunk_size: int = 500,
    overlap: int = 100,
    min_chunk_size: int = 20,
) -> list[RagChunk]:
    '''
    解析扫描 PDF 并做 RAG 分块。

    流程
    ----
    1. pymupdf4llm 检测到无文本层 → 自动触发 OCR → 输出 Markdown
    2. 把所有页拼成一个 Markdown 字符串，记录每行对应的页码
    3. 和纯文本 PDF 完全相同：# 标题划 section，表格成块，正文 sliding window
    '''
    pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)

    lines: list[str] = []
    line_pages: list[int] = []
    for page in pages:
        page_num = page['metadata']['page_number']
        for line in page['text'].splitlines():
            lines.append(line)
            line_pages.append(page_num)

    chunks: list[RagChunk] = []
    current_section = 'General'
    current_page = 1
    buffer = ''
    table_lines: list[str] = []

    def add_chunk(text: str, page: int):
        text = text.strip()
        if len(text) >= min_chunk_size:
            chunks.append(RagChunk(
                text=text,
                source_file=pdf_path.name,
                section=current_section,
                page=page,
                chunk_index=len(chunks),
            ))

    def flush_text():
        nonlocal buffer
        while len(buffer) >= chunk_size:
            add_chunk(buffer[:chunk_size], current_page)
            buffer = buffer[chunk_size - overlap:]
        add_chunk(buffer, current_page)
        buffer = ''

    def flush_table():
        nonlocal table_lines
        if table_lines:
            add_chunk('\n'.join(table_lines), current_page)
            table_lines = []

    for line, page_num in zip(lines, line_pages):
        current_page = page_num
        m = _HEADING_RE.match(line)
        if m:
            flush_text()
            flush_table()
            current_section = re.sub(r'\*+', '', m.group(2)).strip()
        elif _is_table_line(line):
            if buffer.strip():
                flush_text()
            table_lines.append(line.strip())
        else:
            flush_table()
            if line.strip():
                buffer += line + ' '

    flush_table()
    flush_text()
    return chunks

from collections import Counter

pdf_path = Path('multipage-6p.pdf')
chunks = extract_and_chunk(pdf_path)

print(f'文件: {pdf_path.name}')
print(f'RAG 分块: {len(chunks)} 块，总字符: {sum(c.char_count for c in chunks)}')
print()
print('section 分布（按文档顺序）：')
counts = Counter(c.section for c in chunks)
for sec in dict.fromkeys(c.section for c in chunks):
    print(f'  {sec[:45]:45s} → {counts[sec]} 块')

# 预览前 10 块内容
print('=' * 60)
for c in chunks[:10]:
    preview = c.text[:80] + '...' if len(c.text) > 80 else c.text
    print(f'\n[{c.chunk_index:2d}] p.{c.page:2d} section={c.section[:30]:30s} len={c.char_count}')
    print(f'    {preview}')