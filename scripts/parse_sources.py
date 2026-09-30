#!/usr/bin/env python3
"""
parse_sources.py
Парсинг и сверка данных из:
  - snps.annotations.txt
  - samples.qc.txt
  - from_AMP.csv
Результат:
  - out/normalized.json
  - out/reconciliation_report.json
"""

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve()


def detect_root() -> Path:
    """Определяет корень проекта автоматически."""

    # Вариант 1: скрипт в project/scripts/
    if HERE.parent.name == "scripts":
        candidate = HERE.parents[1]
        if (candidate / "data" / "raw").exists():
            return candidate

    # Вариант 2: папка data/ рядом со скриптом
    if (HERE.parent / "data" / "raw").exists():
        return HERE.parent

    # Вариант 3: файлы лежат плоско рядом со скриптом
    if (HERE.parent / "snps.annotations.txt").exists():
        return HERE.parent

    # Вариант 4: запуск из текущей директории проекта
    cwd = Path.cwd()
    if (cwd / "data" / "raw").exists():
        return cwd
    if (cwd / "snps.annotations.txt").exists():
        return cwd

    # Fallback: папка скрипта
    return HERE.parent


ROOT = detect_root()

if (ROOT / "data" / "raw").exists():
    RAW_DIR = ROOT / "data" / "raw"
else:
    RAW_DIR = ROOT

if (ROOT / "data" / "curated").exists():
    CURATED_DIR = ROOT / "data" / "curated"
else:
    CURATED_DIR = ROOT

OUT_DIR = ROOT / "out"

SNPS_TXT = RAW_DIR / "snps.annotations.txt"
QC_TXT = RAW_DIR / "samples.qc.txt"
AMP_CSV = CURATED_DIR / "from_AMP.csv"

NORMALIZED_JSON = OUT_DIR / "normalized.json"
RECONCILIATION_JSON = OUT_DIR / "reconciliation_report.json"


def read_tsv(path: Path):
    """Читает TSV-файл и возвращает список словарей."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quotechar='"')
        try:
            header = next(reader)
        except StopIteration:
            return []

        rows = []
        for row in reader:
            if not row:
                continue
            rows.append(dict(zip(header, row)))
        return rows


def parse_variant_tokens(text: str):
    """
    Извлекает позиции вида 2485T, 6735A, 9541T.
    Возвращает список {"position": int, "base": str}.
    """
    if not text:
        return []

    result = []
    for match in re.finditer(r"\b(\d+)([ACGTacgt])\b", text):
        result.append({
            "position": int(match.group(1)),
            "base": match.group(2).upper()
        })
    return result


def positions_from_variant_tokens(tokens):
    """Возвращает отсортированный список уникальных позиций."""
    return sorted({item["position"] for item in tokens})


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ann_rows = read_tsv(SNPS_TXT)
    qc_rows = read_tsv(QC_TXT)

    # ----------------------------------------------------------
    # 1. SampleID
    # ----------------------------------------------------------
    sample_ids = sorted({
        row.get("SampleID", "").strip('"')
        for row in ann_rows + qc_rows
        if row.get("SampleID")
    })

    # ----------------------------------------------------------
    # 2. Позиции из snps.annotations.txt
    # ----------------------------------------------------------
    annotation_positions = []
    annotation_records = []

    for row in ann_rows:
        pos_raw = (row.get("Position") or "").strip('"')
        if not pos_raw.isdigit():
            continue

        pos = int(pos_raw)
        ref = (row.get("Ref") or "").strip('"').upper()
        alt = (row.get("Alt") or "").strip('"').upper()

        annotation_positions.append(pos)
        annotation_records.append({
            "position": pos,
            "ref": ref,
            "alt": alt
        })

    annotation_positions = sorted(set(annotation_positions))

    # ----------------------------------------------------------
    # 3. Данные из samples.qc.txt
    # ----------------------------------------------------------
    align_positions = set()
    missing_tokens = []
    private_tokens = []
    qc_messages = []
    haplogroups = set()

    for row in qc_rows:
        hg = (row.get("Haplogroup") or "").strip('"')
        if hg:
            haplogroups.add(hg)

        typ = (row.get("Type") or "").strip('"').lower()
        msg = (row.get("Message") or "").strip('"')

        if msg:
            qc_messages.append({
                "type": typ,
                "message": msg
            })

        # Извлекаем ALIGN-позиции из сообщения
        if "ALIGN" in msg.upper():
            for item in parse_variant_tokens(msg):
                align_positions.add(item["position"])

        missing_text = row.get("Missing Mutations") or ""
        private_text = row.get("Global Private Mutations") or ""

        if missing_text:
            missing_tokens.extend(parse_variant_tokens(missing_text))

        if private_text:
            private_tokens.extend(parse_variant_tokens(private_text))

    missing_positions = positions_from_variant_tokens(missing_tokens)
    private_positions = positions_from_variant_tokens(private_tokens)
    align_positions_sorted = sorted(align_positions)

    # ----------------------------------------------------------
    # 4. Expected AMP positions
    # ----------------------------------------------------------
    expected_amp_positions = sorted(
        set(annotation_positions) - align_positions
    )

    # ----------------------------------------------------------
    # 5. Позиции из from_AMP.csv
    # ----------------------------------------------------------
    amp_positions = []
    amp_rows_count = 0

    if AMP_CSV.exists():
        with AMP_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            pos_field = "Позиция (р. мтДНК)"
            if pos_field not in fieldnames and len(fieldnames) > 1:
                pos_field = fieldnames[1]

            for row in reader:
                amp_rows_count += 1
                pos_raw = (row.get(pos_field) or "").strip()
                if pos_raw.isdigit():
                    amp_positions.append(int(pos_raw))

    amp_positions = sorted(set(amp_positions))

    # ----------------------------------------------------------
    # 6. Сверка данных
    # ----------------------------------------------------------
    issues = []
    warnings = []

    if not sample_ids:
        issues.append("SampleID не найден ни в одном источнике.")

    if len(sample_ids) > 1:
        issues.append(
            "Обнаружено несколько SampleID: "
            + ", ".join(sample_ids)
            + ". Требуется явная фильтрация по одному образцу."
        )

    if not annotation_positions:
        issues.append("В snps.annotations.txt не найдено корректных позиций.")

    if not align_positions:
        warnings.append("ALIGN-позиции не распознаны из samples.qc.txt.")

    if len(expected_amp_positions) != len(amp_positions):
        issues.append(
            f"Количество ожидаемых AMP-позиций ({len(expected_amp_positions)}) "
            f"не совпадает с количеством позиций в from_AMP.csv ({len(amp_positions)})."
        )

    missing_in_amp = sorted(set(expected_amp_positions) - set(amp_positions))
    extra_in_amp = sorted(set(amp_positions) - set(expected_amp_positions))

    if missing_in_amp:
        issues.append(
            "Позиции ожидаются после исключения ALIGN, но отсутствуют в from_AMP.csv: "
            + ", ".join(map(str, missing_in_amp))
        )

    if extra_in_amp:
        issues.append(
            "Позиции есть в from_AMP.csv, но не входят в expected AMP set: "
            + ", ".join(map(str, extra_in_amp))
        )

    # ----------------------------------------------------------
    # 7. Проверка пересечения с Global Private Mutations
    #    ALIGN-позиции исключаются из сравнения (ожидаемо)
    # ----------------------------------------------------------
    private_not_expected = sorted(
        (set(private_positions) - set(expected_amp_positions)) - align_positions
    )

    expected_not_private = sorted(
        set(expected_amp_positions) - set(private_positions)
    )

    if private_not_expected:
        issues.append(
            "Global private mutation позиции не входят в expected AMP set "
            "и не являются ALIGN-артефактами: "
            + ", ".join(map(str, private_not_expected))
        )

    if expected_not_private:
        warnings.append(
            "Expected AMP позиции не найдены в Global Private Mutations "
            "(могут быть кураторскими): "
            + ", ".join(map(str, expected_not_private))
        )

    # ----------------------------------------------------------
    # 8. Кураторские позиции без подтверждения в private
    # ----------------------------------------------------------
    curated_not_in_private = sorted(
        set(amp_positions) - set(private_positions) - align_positions
    )

    if curated_not_in_private:
        warnings.append(
            "Кураторские позиции без подтверждения в Global Private Mutations: "
            + ", ".join(map(str, curated_not_in_private))
        )

    # ----------------------------------------------------------
    # 9. Результат
    # ----------------------------------------------------------
    normalized = {
        "sample_ids": sample_ids,
        "haplogroups": sorted(haplogroups),
        "annotation_positions": annotation_positions,
        "annotation_records": annotation_records,
        "align_positions": align_positions_sorted,
        "expected_amp_positions": expected_amp_positions,
        "missing_positions": missing_positions,
        "private_positions": private_positions,
        "qc_messages": qc_messages,
        "amp_csv_positions": amp_positions,
        "amp_csv_rows": amp_rows_count
    }

    reconciliation = {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "warnings": warnings,
        "counts": {
            "annotation_positions": len(annotation_positions),
            "align_positions": len(align_positions_sorted),
            "expected_amp_positions": len(expected_amp_positions),
            "amp_csv_positions": len(amp_positions),
            "amp_csv_rows": amp_rows_count,
            "missing_positions": len(missing_positions),
            "private_positions": len(private_positions)
        }
    }

    NORMALIZED_JSON.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    RECONCILIATION_JSON.write_text(
        json.dumps(reconciliation, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Normalized: {NORMALIZED_JSON}")
    print(f"Reconciliation: {RECONCILIATION_JSON}")
    print(f"Status: {reconciliation['status']}")

    if issues:
        print("\nIssues:")
        for issue in issues:
            print("  -", issue)

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print("  -", warning)


if __name__ == "__main__":
    main()
