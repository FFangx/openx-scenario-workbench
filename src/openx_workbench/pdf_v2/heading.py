import re
_SECTION_ID_RE = re.compile('^(\\d+\\.\\d+(?:\\.\\d+){0,4}|[A-Z]\\.\\d+(?:\\.\\d+){0,4}|[A-Z]\\d+\\.\\d+(?:\\.\\d+)?)')
_TOP_LEVEL_SECTION_RE = re.compile('^(\\d{1,2})(?!\\s*[\\.．]\\s*\\d)\\b')
_CHAPTER_NUM_RE = re.compile('^(?:第\\s*)?(\\d{1,2})\\s*章\\b')
_ANNEX_ID_RE = re.compile('^附\\s*录\\s*([A-Z])', re.IGNORECASE)

def extract_section_id(title: str) -> str:
    title = title.strip()
    m = _ANNEX_ID_RE.match(title)
    if m:
        return m.group(1).upper()
    m = _CHAPTER_NUM_RE.match(title)
    if m:
        return m.group(1)
    m = _TOP_LEVEL_SECTION_RE.match(title)
    if m:
        return m.group(1)
    m = _SECTION_ID_RE.match(title)
    if m:
        return m.group(1)
    return title[:20]
