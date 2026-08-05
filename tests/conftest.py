from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_MANAGER_SRC = PROJECT_ROOT / "src" / "task_manager"

sys.path.insert(0, str(TASK_MANAGER_SRC))


@pytest.fixture(autouse=True)
def disable_langfuse_export(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep deterministic tests independent from an external Langfuse instance."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
