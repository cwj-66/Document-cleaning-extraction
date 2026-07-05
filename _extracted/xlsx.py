import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl


def clean_text(text: str) -> str:
    '''合并连续空白，去首尾空白。'''
    return re.sub(r'\s+', ' ', str(text)).strip()


@dataclass
class Element:
    '''解析出的一个表格元素。'''
    index: int
    category: str   # Table / Title
    text: str
    sheet: str = ''  # 仅 xlsx 有值


@dataclass
class RagChunk:
    '''RAG 一块数据，带元信息方便检索。'''
    text: str
    source_file: str
    section: str
    chunk_index: int
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)


def _csv_rows(path: Path, sep: str) -> list[list[str]]:
    '''读 csv / tsv，自动处理 UTF-8 BOM。'''
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.reader(f, delimiter=sep))


def _xlsx_sheets(path: Path) -> dict[str, list[list[str]]]:
    '''读 xlsx，跳过空 sheet。'''
    wb = openpyxl.load_workbook(path, data_only=True)
    result = {}
    for ws in wb.worksheets:
        rows = [['' if c.value is None else str(c.value) for c in row]
                for row in ws.iter_rows()]
        if any(any(clean_text(c) for c in row) for row in rows):
            result[ws.title] = rows
    return result


def extract(file_path: Path) -> list[Element]:
    '''按扩展名读表，处理脏表头，返回 Element 列表。'''
    suffix = file_path.suffix.lower()
    if suffix == '.csv':
        sheets = {'': _csv_rows(file_path, ',')}
    elif suffix == '.tsv':
        sheets = {'': _csv_rows(file_path, '\t')}
    elif suffix == '.xlsx':
        sheets = _xlsx_sheets(file_path)
    else:
        raise ValueError(f'不支持：{suffix}')

    elements: list[Element] = []
    for sheet, rows in sheets.items():
        if not rows:
            continue
        if len(rows) >= 2:
            n0 = sum(bool(clean_text(c)) for c in rows[0])
            n1 = sum(bool(clean_text(c)) for c in rows[1])
            if n0 < n1:
                title = clean_text(' '.join(c for c in rows[0] if clean_text(c)))
                elements.append(Element(len(elements), 'Title', title, sheet))
                rows = rows[1:]
        lines = [' | '.join(clean_text(c) for c in row)
                 for row in rows if any(clean_text(c) for c in row)]
        if lines:
            elements.append(Element(len(elements), 'Table', '\n'.join(lines), sheet))
    return elements


def chunk_elements(
    elements: list[Element],
    source_file: str,
    min_chunk_size: int = 5,
) -> list[RagChunk]:
    '''Title 更新 section；Table 整表成一块。'''
    chunks: list[RagChunk] = []
    current_section = source_file
    for el in elements:
        if el.category == 'Title':
            current_section = el.text
        elif el.category == 'Table':
            section = f'{current_section} [{el.sheet}]' if el.sheet else current_section
            if len(el.text.strip()) >= min_chunk_size:
                chunks.append(RagChunk(
                    text=el.text.strip(),
                    source_file=source_file,
                    section=section,
                    chunk_index=len(chunks),
                ))
    return chunks

base = Path('.')
all_files = [
    base / 'game-items-zh.csv',
    base / 'game-items-zh.tsv',
    base / 'game-items-zh.xlsx',
    base / 'stanley-cups.csv',
    base / 'stanley-cups.tsv',
    base / 'stanley-cups.xlsx',
]

for fp in all_files:
    chunks = chunk_elements(extract(fp), source_file=fp.name)
    print(f'[{fp.name}] {len(chunks)} 块')
    for c in chunks:
        print(f'  chunk {c.chunk_index} | section={c.section} | len={c.char_count}')
        for line in c.text.split('\n'):
            print(f'    {line}')
    print()