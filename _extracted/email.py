import email
import email.policy
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup


def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.replace('\t', ' ')).strip()


@dataclass
class EmailMeta:
    subject: str = ''
    sender: str = ''
    recipients: str = ''
    date: str = ''
    message_id: str = ''


@dataclass
class Element:
    index: int
    category: str   # Subject / Header / Title / ListItem / Table / NarrativeText / Attachment
    text: str


_QUOTE_SPLITTERS = [
    re.compile(r'^-----Original Message-----', re.I | re.M),
    re.compile(r'^-------- Forwarded Message --------', re.I | re.M),
    re.compile(r'^On .+ wrote:\s*$', re.I | re.M),
    re.compile(r'^在 .+ 写道：\s*$', re.M),
]
_CN_HEADING_RE = re.compile(
    r'^(?:[一二三四五六七八九十百]+[、.]'
    r'|第[一二三四五六七八九十\d]+[章节条]'
    r'|SECTION\s+\d+'
    r'|\d+\.\s)'
)
_LIST_RE = re.compile(r'^[-*•]\s+|^\d+\.\s+')


def strip_quoted_reply(text: str) -> str:
    for pat in _QUOTE_SPLITTERS:
        if m := pat.search(text):
            return text[:m.start()].rstrip()
    for i, line in enumerate(text.splitlines()):
        if line.strip().startswith('>'):
            return '\n'.join(text.splitlines()[:i]).rstrip()
    return text.rstrip()


def strip_signature(text: str) -> str:
    if m := re.search(r'\n--\s*\n', text):
        return text[:m.start()].rstrip()
    return text.rstrip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(['script', 'style']):
        tag.decompose()
    for tag in soup.select('div.gmail_quote, blockquote'):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r'gmail_signature|signature', re.I)):
        tag.decompose()
    return soup.get_text('\n', strip=True)


def get_body_text(msg: email.message.EmailMessage, prefer_plain: bool = True) -> str:
    pref = ('plain', 'html') if prefer_plain else ('html', 'plain')
    part = msg.get_body(preferencelist=pref)
    if not part:
        return ''
    content = part.get_content()
    if not isinstance(content, str):
        return ''
    return html_to_text(content) if part.get_content_type() == 'text/html' else content


def is_section_heading(line: str) -> bool:
    s = line.strip()
    return bool(s) and len(s) < 80 and (
        bool(_CN_HEADING_RE.match(s)) or (s.isupper() and len(s.split()) <= 8)
    )

def body_to_elements(body: str) -> list[Element]:
    elements: list[Element] = []
    for block in re.split(r'\n\s*\n', body.strip()):
        block = block.strip()
        if not block:
            continue
        lines = [ln.rstrip() for ln in block.split('\n') if ln.strip()]
        if not lines:
            continue

        if len(lines) >= 2 and all('|' in ln for ln in lines):
            rows = [
                ' | '.join(clean_text(c) for c in ln.strip('|').split('|'))
                for ln in lines
                if not re.match(r'^[\|\s\-:]+$', ln)
            ]
            if rows:
                elements.append(Element(len(elements), 'Table', '\n'.join(rows)))
            continue

        if all(_LIST_RE.match(ln.strip()) for ln in lines):
            for ln in lines:
                elements.append(Element(len(elements), 'ListItem', clean_text(_LIST_RE.sub('', ln.strip()))))
            continue

        if is_section_heading(lines[0]) and len(lines) == 1:
            elements.append(Element(len(elements), 'Title', clean_text(lines[0])))
            continue

        elements.append(Element(len(elements), 'NarrativeText', clean_text('\n'.join(lines))))
    return elements


def extract(eml_path: Path, prefer_plain: bool = True) -> tuple[EmailMeta, list[Element]]:
    with open(eml_path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)

    meta = EmailMeta(
        subject=msg.get('Subject', '') or '',
        sender=msg.get('From', '') or '',
        recipients=msg.get('To', '') or '',
        date=msg.get('Date', '') or '',
        message_id=(msg.get('Message-ID', '') or '').strip('<>'),
    )

    body = strip_signature(strip_quoted_reply(get_body_text(msg, prefer_plain)))
    elements: list[Element] = []

    if meta.subject:
        elements.append(Element(len(elements), 'Subject', clean_text(meta.subject)))
    header = ' | '.join(x for x in (
        f'发件人: {meta.sender}' if meta.sender else '',
        f'收件人: {meta.recipients}' if meta.recipients else '',
        f'日期: {meta.date}' if meta.date else '',
    ) if x)
    if header:
        elements.append(Element(len(elements), 'Header', header))

    elements.extend(body_to_elements(body))
    for part in msg.iter_attachments():
        fname = part.get_filename() or '(未命名)'
        elements.append(Element(len(elements), 'Attachment', f'[附件: {fname} | 类型: {part.get_content_type()}]'))

    return meta, elements

from collections import Counter


eml_path = Path('reply-with-quote.eml')

meta, elements = extract(eml_path)
body_chars = sum(len(e.text) for e in elements if e.category not in ('Subject', 'Header'))
print(f'{eml_path.name}: {meta.subject}')
print(f'元素 {len(elements)} 个 → {dict(Counter(e.category for e in elements))} | 正文 {body_chars} 字')

for e in elements:
    p = e.text[:70] + '...' if len(e.text) > 70 else e.text
    print(f'[{e.index:2d}] {e.category:12s} {p}')

@dataclass
class RagChunk:
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
    chunks: list[RagChunk] = []
    section, buf = 'General', ''

    def add(text: str):
        if len(text.strip()) >= min_chunk_size:
            chunks.append(RagChunk(text.strip(), source_file, section, len(chunks)))

    def flush():
        nonlocal buf
        add(buf)
        buf = ''

    def feed(text: str):
        nonlocal buf
        buf += text
        while len(buf) >= chunk_size:
            add(buf[:chunk_size])
            buf = buf[chunk_size - overlap:]

    for el in elements:
        if el.category in ('Subject', 'Header'):
            flush()
            add(el.text)
        elif el.category == 'Title':
            flush()
            section = el.text
        elif el.category in ('Table', 'Attachment'):
            flush()
            add(el.text)
        elif el.category == 'ListItem':
            feed('- ' + el.text + '\n')
        else:
            feed(el.text + '\n')
    flush()
    return chunks

chunks = chunk_elements(elements, eml_path.name)
print(f'[{eml_path.name}] {len(chunks)} 块')
for c in chunks:
    p = c.text[:60] + '...' if len(c.text) > 60 else c.text
    print(f'  {c.chunk_index:2d} | {c.section[:24]:24s} | {p}')