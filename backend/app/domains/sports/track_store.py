"""GPX 轨迹文件存取（纯本地文件实现，M4.5-tracks Task 1）。

存储布局：backend/uploads/tracks/{uuid4hex}.gpx；数据库侧只保存相对 key
"tracks/{uuid4hex}.gpx"。读取前用正则白名单校验 key（仅接受 save_gpx 生成的
唯一形态），杜绝路径穿越；校验后去掉 "tracks/" 前缀定位物理文件。
"""

import re
import uuid
from pathlib import Path

# backend/app/domains/sports/track_store.py → parents[3] = backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
uploads_dir = _BACKEND_ROOT / "uploads" / "tracks"

_KEY_RE = re.compile(r"^tracks/[0-9a-f]{32}\.gpx$")


def save_gpx(content: bytes) -> str:
    """写入 GPX 字节并返回相对 key；目录惰性创建（后缀/大小校验由调用方负责）。"""
    name = uuid.uuid4().hex + ".gpx"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / name).write_bytes(content)
    return f"tracks/{name}"


def read_gpx(key: str) -> str:
    """按 key 读取 GPX 文本；非法 key（含路径穿越形态）一律 ValueError。

    fullmatch 而非 match+$：`$` 会匹配末尾换行前，"tracks/xx.gpx\\n" 结尾的
    key 可绕过 match；fullmatch 锚定整个串，无此绕过。
    """
    if _KEY_RE.fullmatch(key) is None:
        raise ValueError("非法轨迹文件标识")
    return (uploads_dir / key.removeprefix("tracks/")).read_text(encoding="utf-8")
