#!/usr/bin/env python3
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONFIG = ROOT / "config" / "deploy_manifest.json"
SITE = ROOT / "site"
OUT_DIR = ROOT / "out"
REPORT = OUT_DIR / "deployment_report.json"

DEFAULT_PROHIBITED = [
    "no4959",
    "I5a1a",
    "SampleID",
    "##fileformat=VCF",
    "FASTQ",
    "BAM",
    "PRIVATE KEY",
    "BEGIN OPENSSH",
    "aws_access_key_id",
    "NETLIFY_AUTH_TOKEN",
]

RAW_EXTENSIONS = {
    ".txt",
    ".csv",
    ".tsv",
    ".vcf",
    ".bam",
    ".sam",
    ".cram",
    ".fastq",
    ".fq",
    ".gz",
    ".zip",
    ".tar",
}

ALLOWED_EXTENSIONS_DEFAULT = {
    ".html",
    ".toml",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey|secret|token|password|passwd|pwd)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}"),
    re.compile(r"BEGIN\s+(RSA|OPENSSH|EC|DSA|PGP)\s+PRIVATE\s+KEY"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
]


def load_manifest():
    if not CONFIG.exists():
        raise SystemExit(f"Missing manifest: {CONFIG}")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(site: Path):
    files = []
    for path in site.rglob("*"):
        if path.is_file():
            files.append(path)
    return files


def check_manifest(manifest):
    errors = []
    warnings = []

    target = os.environ.get("DEPLOY_TARGET", "netlify-drop-demo")

    if manifest.get("classification") == "real":
        errors.append("Real data cannot be deployed to public Netlify.")

    if manifest.get("contains_personal_data") is True:
        errors.append("Personal data cannot be deployed to public Netlify.")

    if manifest.get("contains_special_category_data") is True:
        errors.append("Special category data cannot be deployed to public Netlify.")

    if manifest.get("contains_biometric_context") is True:
        errors.append("Biometric context cannot be deployed to public Netlify.")

    if manifest.get("public_deploy_allowed") is False:
        errors.append("public_deploy_allowed=false.")

    if target not in manifest.get("allowed_targets", []):
        errors.append(f"Deploy target '{target}' is not allowed.")

    if manifest.get("classification") in {"sanitized", "aggregated", "derived"}:
        for field in ["data_approver", "security_approver", "legal_approver", "approval_date"]:
            if not manifest.get(field):
                errors.append(f"Missing approval field: {field}")

    if not manifest.get("dataset_id"):
        warnings.append("dataset_id is empty.")

    return errors, warnings


def check_site_structure(manifest, files):
    errors = []
    warnings = []

    if not SITE.exists():
        errors.append("site/ directory does not exist.")
        return errors, warnings

    index_html = SITE / "index.html"
    if not index_html.exists():
        errors.append("site/index.html is required for Netlify Drop.")

    allowed_ext = set(manifest.get("allowed_extensions", list(ALLOWED_EXTENSIONS_DEFAULT)))
    if isinstance(allowed_ext, list):
        allowed_ext = {e.lower() for e in allowed_ext}

    for path in files:
        rel = path.relative_to(SITE)
        ext = path.suffix.lower()

        if ext in RAW_EXTENSIONS:
            errors.append(f"Raw/sensitive file extension found in site/: {rel}")

        if allowed_ext and ext not in allowed_ext:
            errors.append(f"Disallowed file type in site/: {rel}")

    # Для строгого демо можно разрешить только index.html и netlify.toml.
    allowed_names = {"index.html", "netlify.toml"}
    unexpected = [
        str(path.relative_to(SITE))
        for path in files
        if str(path.relative_to(SITE)) not in allowed_names
    ]
    if unexpected:
        warnings.append(
            "Unexpected files in site/; strict mode may fail: "
            + ", ".join(unexpected)
        )

    return errors, warnings


def check_sizes(manifest, files):
    errors = []
    warnings = []

    max_site_bytes = int(manifest.get("max_site_bytes", 50 * 1024 * 1024))
    max_file_bytes = int(manifest.get("max_file_bytes", 10 * 1024 * 1024))
    max_files = int(manifest.get("max_files", 54000))

    total = sum(path.stat().st_size for path in files)

    if total > max_site_bytes:
        errors.append(f"Total site size {total} exceeds max_site_bytes {max_site_bytes}.")

    if len(files) > max_files:
        errors.append(f"File count {len(files)} exceeds max_files {max_files}.")

    for path in files:
        size = path.stat().st_size
        if size > max_file_bytes:
            errors.append(f"File {path.relative_to(SITE)} size {size} exceeds max_file_bytes {max_file_bytes}.")

    return errors, warnings


def check_content(manifest, files):
    errors = []
    warnings = []

    prohibited = list(dict.fromkeys(DEFAULT_PROHIBITED + manifest.get("prohibited_strings", [])))

    for path in files:
        if path.suffix.lower() not in {".html", ".toml", ".css", ".js", ".json"}:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            warnings.append(f"Cannot read {path.relative_to(SITE)}: {exc}")
            continue

        for token in prohibited:
            if token and token.lower() in text.lower():
                errors.append(f"Prohibited string '{token}' found in {path.relative_to(SITE)}.")

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"Possible secret pattern found in {path.relative_to(SITE)}.")

    if manifest.get("require_disclaimer", True):
        index_html = SITE / "index.html"
        if index_html.exists():
            text = index_html.read_text(encoding="utf-8", errors="ignore").lower()
            required_phrases = [
                "не является медицинским заключением",
                "demo",
                "демо",
            ]
            if not any (phrase in text for phrase in required_phrases):
                errors.append("Required medical/demo disclaimer not found in index.html.")

    return errors, warnings


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    if not SITE.exists():
        raise SystemExit("site/ does not exist. Run build_site.py first.")

    files = collect_files(SITE)

    all_errors = []
    all_warnings = []

    for checker in [
        lambda: check_manifest(manifest),
        lambda: check_site_structure(manifest, files),
        lambda: check_sizes(manifest, files),
        lambda: check_content(manifest, files),
    ]:
        errors, warnings = checker()
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    file_hashes = {
        str(path.relative_to(SITE)): sha256_file(path)
        for path in files
    }

    report = {
        "status": "PASS" if not all_errors else "FAIL",
        "target": os.environ.get("DEPLOY_TARGET", "netlify-drop-demo"),
        "dataset_id": manifest.get("dataset_id"),
        "version": manifest.get("version"),
        "classification": manifest.get("classification"),
        "errors": all_errors,
        "warnings": all_warnings,
        "file_hashes_sha256": file_hashes,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Deployment report: {REPORT}")
    print(f"Status: {report['status']}")

    if all_warnings:
        print("Warnings:")
        for w in all_warnings:
            print(" -", w)

    if all_errors:
        print("Errors:", file=sys.stderr)
        for e in all_errors:
            print(" -", e, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
