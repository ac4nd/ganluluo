"""Export the FastAPI OpenAPI schema to stdout (redirect to openapi.json).

Works both as `python -m scripts.export_openapi` and
`python scripts/export_openapi.py`: the parent of scripts/ (the backend
package root containing `app`) is prepended to sys.path so `app.main`
is importable regardless of how the interpreter was invoked.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
