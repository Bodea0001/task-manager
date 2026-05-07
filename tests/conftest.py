from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_MANAGER_SRC = PROJECT_ROOT / "src" / "task_manager"

sys.path.insert(0, str(TASK_MANAGER_SRC))
