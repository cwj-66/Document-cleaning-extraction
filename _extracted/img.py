import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from openai import OpenAI
from PIL import Image

_CAPTION_MODEL = 'qwen3.6-flash'
_OCR_LANG = 'chi_sim+eng'

# ---------- 本地检测阈值（可按样例微调）----------
_TEXT_MIN_CHARS    = 30    # OCR 字数 >= 此值 → 认为有文字
_TABLE_THRESH      = 150   # 二值化阈值（越低越敏感）
_TABLE_MIN_HLINES  = 4     # 足够长的水平线数量
_TABLE_MIN_VLINES  = 1     # 足够长的垂直线数量
_TABLE_MIN_HW_RATIO = 0.35 # 水平线宽度 >= 图宽 × 此比例
_TABLE_MIN_VH_RATIO = 0.08 # 垂直线高度 >= 图高 × 此比例
_TABLE_MIN_WHITE   = 0.45  # 白底占比 >= 此值（过滤照片误报）
_PHOTO_MAX_CHARS   = 30    # OCR 字数 <  此值 → 可能是照片
_PHOTO_MIN_SAT     = 35    # HSV 饱和度均值 >= 此值 → 认为有照片/彩图

# Windows：Tesseract 路径
_TESS_EXE = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
_TESSDATA  = Path(r'C:\Program Files\Tesseract-OCR\tessdata')
if _TESS_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(_TESS_EXE)
if _TESSDATA.exists():
    os.environ['TESSDATA_PREFIX'] = str(_TESSDATA)


@dataclass
class RagChunk:
    '''图片识别后的一个 RAG 分块。'''
    text:        str
    source_file: str
    section:     str
    page:        int
    chunk_index: int
    image_path:  str = ''
    char_count:  int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)

# ============================================================
# 本地检测（零 API）
# ============================================================

def _ocr_raw(img_path: Path, lang: str = _OCR_LANG) -> str:
    '''Tesseract OCR，返回原始字符串。'''
    return pytesseract.image_to_string(Image.open(img_path), lang=lang).strip()


def _has_table(img_path: Path) -> bool:
    '''
    用 OpenCV 检测表格网格线。

    条件（同时满足）：
    1. 白底占比高（过滤照片里的自然线条误报）
    2. 足够长的水平线 >= _TABLE_MIN_HLINES
    3. 足够长的垂直线 >= _TABLE_MIN_VLINES
    '''
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False

    h, w = img.shape
    white_ratio = float((img > 230).mean())
    if white_ratio < _TABLE_MIN_WHITE:
        return False

    _, binary = cv2.threshold(img, _TABLE_THRESH, 255, cv2.THRESH_BINARY_INV)

    # 提取水平线，只统计宽度足够的
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(w * 0.2), 20), 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    h_contours, _ = cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    long_h = sum(1 for c in h_contours if cv2.boundingRect(c)[2] >= w * _TABLE_MIN_HW_RATIO)

    # 提取垂直线，只统计高度足够的
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(int(h * 0.08), 10)))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
    v_contours, _ = cv2.findContours(v_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    long_v = sum(1 for c in v_contours if cv2.boundingRect(c)[3] >= h * _TABLE_MIN_VH_RATIO)

    return long_h >= _TABLE_MIN_HLINES and long_v >= _TABLE_MIN_VLINES


def _mean_saturation(img_path: Path) -> float:
    '''返回图片 HSV 饱和度均值（0–255）。'''
    img = cv2.imread(str(img_path))
    if img is None:
        return 0.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return float(np.mean(hsv[:, :, 1]))


def detect_components(img_path: Path, lang: str = _OCR_LANG) -> tuple[set[str], str]:
    '''
    本地检测图片包含哪些成分，返回 (成分集合, ocr原始文字)。

    成分集合可包含：'text' / 'table' / 'photo'
    ocr 文字顺便一起返回，避免后面重复跑一次 Tesseract。
    '''
    ocr_text = _ocr_raw(img_path, lang=lang)
    components: set[str] = set()

    if len(ocr_text) >= _TEXT_MIN_CHARS:
        components.add('text')

    if _has_table(img_path):
        components.add('table')

    sat = _mean_saturation(img_path)
    if len(ocr_text) < _PHOTO_MAX_CHARS or sat >= _PHOTO_MIN_SAT:
        components.add('photo')

    # 兜底：三者都没检测到 → 强制 OCR 一次
    if not components:
        components.add('text')

    return components, ocr_text

# ============================================================
# API 提取（按需调用）
# ============================================================

def _llm_call(img_path: str, prompt: str) -> str:
    '''向百炼发送图片 + 文字 prompt，返回模型回复。'''
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
                {'type': 'text', 'text': prompt},
            ],
        }],
    )
    return resp.choices[0].message.content


_PROMPT_TABLE = (
    '请把图片中的表格还原为 Markdown 表格格式，保留所有行列和数据；'
    '若有合并单元格，用说明文字标注；不需要解释，直接输出 Markdown。'
)
_PROMPT_PHOTO = (
    '用 2–3 句中文概括图片主要内容；'
    '不要写构图、层次感、背景虚化等摄影术语。'
)


# ============================================================
# 主函数
# ============================================================

def extract_and_chunk(
    img_path: Path,
    lang: str = _OCR_LANG,
    with_api: bool = True,
) -> list[RagChunk]:
    '''
    单张图片 → 1 个 chunk。

    流程
    ----
    1. 本地检测成分（text / table / photo，可多选）
    2. 按成分分支处理：
       - text  → Tesseract OCR（本地）
       - table → 百炼还原 Markdown 表格
       - photo → 百炼 2–3 句简短描述
    3. 拼成 1 个 chunk

    参数
    ----
    with_api : False 时跳过所有 API 调用（只跑 OCR），方便离线测试
    '''
    img_path = Path(img_path)
    components, ocr_text = detect_components(img_path, lang=lang)

    parts = [f'[图片: {img_path.name}]']
    parts.append(f'成分: {" + ".join(sorted(components))}')

    # --- text：直接用已有 OCR 结果 ---
    if 'text' in components:
        parts.append(f'OCR:\n{ocr_text}' if ocr_text else 'OCR: （未识别到文字）')

    # --- table：百炼还原 Markdown ---
    if 'table' in components and with_api:
        md_table = _llm_call(str(img_path), _PROMPT_TABLE)
        parts.append(f'表格:\n{md_table}')

    # --- photo：百炼简短描述 ---
    if 'photo' in components and with_api:
        desc = _llm_call(str(img_path), _PROMPT_PHOTO)
        parts.append(f'描述: {desc}')

    return [RagChunk(
        text='\n'.join(parts),
        source_file=img_path.name,
        section='General',
        page=1,
        chunk_index=0,
        image_path=str(img_path.resolve()),
    )]

# 单文件测试（先不调 API，只看本地检测结果）
img_path = Path('DA-1p.png')

comps, ocr = detect_components(img_path)
print(f'文件: {img_path.name}')
print(f'检测成分: {comps}')
print(f'OCR 字数: {len(ocr)}')
print('=' * 60)

# 完整跑（含 API）
chunks = extract_and_chunk(img_path)
c = chunks[0]
print(f'chunk 字符: {c.char_count}')
print(c.text)

# 批量跑 img/ 目录下所有图片
img_dir  = Path('.')
img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
img_files = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in img_exts)

all_chunks: dict[str, list[RagChunk]] = {}

for img in img_files:
    comps, _ = detect_components(img)
    print(f'处理: {img.name:<40s} 成分: {comps}')
    chunks = extract_and_chunk(img)
    all_chunks[img.name] = chunks
    print(f'  → {len(chunks)} 块，{sum(c.char_count for c in chunks)} 字')

print('\n全部完成。')

# 预览每个文件的结果
print('=' * 60)
for fname, chunks in all_chunks.items():
    if not chunks:
        continue
    c = chunks[0]
    preview = c.text[:150] + '...' if len(c.text) > 150 else c.text
    print(f'{fname}  len={c.char_count}')
    print(preview)
    print()