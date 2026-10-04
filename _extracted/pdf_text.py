"""Generated from workshops/pdf/纯文本.pdf/clean-pure-text.ipynb; edit the notebook, then re-export."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf4llm


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
    解析纯文本 PDF 并做 RAG 分块。

    流程
    ----
    1. pymupdf4llm 将每页转为 Markdown，自动处理双栏/标题/表格
    2. 把所有页拼成一个大 Markdown 字符串，同时记录每行对应的页码
    3. 按 # 标题行划定 section；表格单独成块；正文 section 内超长再 sliding window
    '''
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")
    if min_chunk_size <= 0:
        raise ValueError("min_chunk_size must be positive")
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
        if page_num != current_page:
            flush_table()
            flush_text()
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
