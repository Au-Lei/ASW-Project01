"""Build an allowlisted server release; never include local keys or business data."""

import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ("app.py", "requirements.txt", "app", "assets", "prompts", "data/field_aliases.json",
           "scripts/manage_users.py", "scripts/backup_data.py")


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in INCLUDE:
            source = ROOT / item
            paths = source.rglob("*") if source.is_dir() else [source]
            for path in paths:
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    archive.write(path, path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：python scripts/build_server_release.py 输出.zip")
    build(Path(sys.argv[1]).resolve())
