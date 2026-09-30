#!/usr/bin/env python3
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DIST = ROOT / "dist"
ZIP_PATH = DIST / "mtdna-dashboard.zip"


def main():
    if not SITE.exists():
        raise SystemExit("site/ does not exist.")

    DIST.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in SITE.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(SITE))

    print(f"Created: {ZIP_PATH}")


if __name__ == "__main__":
    main()
