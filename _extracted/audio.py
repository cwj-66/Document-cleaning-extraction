from dataclasses import dataclass, field
from pathlib import Path

import whisper


@dataclass
class RagChunk:
    '''音频转写后的一个 RAG 分块。'''
    text:        str
    source_file: str
    section:     str        # 音频无版式结构，固定为 'General'
    start_time:  float      # 块起始时间（秒）
    end_time:    float      # 块结束时间（秒）
    chunk_index: int
    char_count:  int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)

def transcribe_and_chunk(
    audio_path: Path,
    model_name: str = 'base',
    language: str | None = None,
    chunk_size: int = 400,
    overlap_segs: int = 1,
) -> list[RagChunk]:
    '''
    转写音频并做 RAG 分块。

    流程
    ----
    1. Whisper 转写 → segment 列表，每个 segment 有 text / start / end
    2. 把相邻 segment 累积到 chunk_size 字以内，超出则结束当前块
    3. overlap_segs：新块从上一块最后 N 个 segment 开始，防语义截断

    参数
    ----
    language : 手动指定语言代码（'zh' / 'en'），None 则 Whisper 自动检测
    chunk_size : 每块最大字符数
    overlap_segs : 块间重叠的 segment 数量
    '''
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language=language)
    segments = result['segments']  # list of {id, start, end, text, ...}

    chunks: list[RagChunk] = []
    buf_text = ''
    buf_start = 0.0
    buf_end = 0.0
    buf_segs: list[dict] = []   # 当前块积累的 segment，用于 overlap

    def flush(segs: list[dict]):
        text = ''.join(s['text'] for s in segs).strip()
        if not text:
            return
        chunks.append(RagChunk(
            text=text,
            source_file=audio_path.name,
            section='General',
            start_time=round(segs[0]['start'], 2),
            end_time=round(segs[-1]['end'], 2),
            chunk_index=len(chunks),
        ))

    for seg in segments:
        seg_text = seg['text'].strip()
        if len(buf_text) + len(seg_text) > chunk_size and buf_segs:
            # 当前块已满 → 输出，然后用尾部 overlap_segs 个 segment 开始新块
            flush(buf_segs)
            buf_segs = buf_segs[-overlap_segs:] if overlap_segs else []
            buf_text = ''.join(s['text'] for s in buf_segs)
        buf_segs.append(seg)
        buf_text += seg_text

    if buf_segs:
        flush(buf_segs)

    return chunks

# 单文件测试
audio_path = Path('test01_20s.wav')

chunks = transcribe_and_chunk(audio_path, language=None)

print(f'文件: {audio_path.name}')
print(f'RAG 分块: {len(chunks)} 块，总字符: {sum(c.char_count for c in chunks)}')
print('=' * 60)
for c in chunks:
    print(f'[{c.chunk_index}] {c.start_time:.1f}s – {c.end_time:.1f}s  len={c.char_count}')
    print(c.text)
    print()

# 批量跑 media/ 目录下所有 wav
import wave

media_dir = Path('.')
wav_files = sorted(media_dir.glob('*.wav'))

# 根据文件名猜语言：chinese → zh，其余 → en
def guess_lang(name: str) -> str:
    return 'zh' if 'chinese' in name else 'en'

all_chunks: dict[str, list[RagChunk]] = {}

for wav in wav_files:
    with wave.open(str(wav)) as w:
        dur = round(w.getnframes() / w.getframerate(), 1)
    lang = guess_lang(wav.name)
    print(f'处理: {wav.name}  ({dur}s, lang={lang})')
    chunks = transcribe_and_chunk(wav, language=lang)
    all_chunks[wav.name] = chunks
    print(f'  → {len(chunks)} 块，{sum(c.char_count for c in chunks)} 字')

print('\n全部完成。')

# 预览每个文件的第一块
print('=' * 60)
for fname, chunks in all_chunks.items():
    if not chunks:
        continue
    c = chunks[0]
    preview = c.text[:100] + '...' if len(c.text) > 100 else c.text
    print(f'{fname}')
    print(f'  [{c.chunk_index}] {c.start_time:.1f}s–{c.end_time:.1f}s  len={c.char_count}')
    print(f'  {preview}')
    print()