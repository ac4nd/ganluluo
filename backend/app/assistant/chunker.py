"""文本分块：按 \\n 与句号切句，聚合到 size 上限，块间携带尾串 overlap。"""


def _sentences(text: str) -> list[str]:
    """切句：句内按 `。` 断开（保留句号），行尾以 `\\n` 收尾；空句丢弃。"""
    out: list[str] = []
    for line in text.split("\n"):
        parts = line.split("。")
        for i, part in enumerate(parts):
            stripped = part.strip()
            if not stripped:
                continue
            out.append(stripped + ("。" if i < len(parts) - 1 else "\n"))
    return out


def chunk_text(text: str, size: int = 600, overlap: int = 80) -> list[str]:
    """切段：句子聚合到 ≤size；单句超长硬切；后续块前缀携带上一块 ≤overlap 尾串。

    返回块内容长度恒 ≤ size + overlap（overlap 尾串不计入 size 预算）。
    """
    units: list[str] = []
    for sent in _sentences(text):
        if len(sent) <= size:
            units.append(sent)
        else:  # 单句超长：按 size 硬切，末片保留收尾符
            for i in range(0, len(sent), size):
                units.append(sent[i:i + size])

    raw: list[str] = []
    cur = ""
    for unit in units:
        if cur and len(cur) + len(unit) > size:
            raw.append(cur)
            cur = unit
        else:
            cur += unit
    if cur:
        raw.append(cur)

    chunks: list[str] = []
    for i, body in enumerate(raw):
        if i > 0 and overlap > 0:
            chunks.append(raw[i - 1][-overlap:] + body)
        else:
            chunks.append(body)
    return [c.rstrip("\n") for c in chunks]
