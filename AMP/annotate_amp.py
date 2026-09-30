#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
annotate_amp.py

Гибкий скрипт для подготовки предварительной таблицы в формате from_AMP.csv
по методологии AMP.pdf на основе входных файлов:

  1) snps.annotations.txt
     Колонки: SampleID, Position, Ref, Alt

  2) samples.qc.txt
     Колонки: SampleID, Haplogroup, Type, Message,
              Missing Mutations, Global Private Mutations

Конфигурация аннотаций и правил вынесена в внешний файл:
  - amp_config.json

Скрипт работает полностью локально, не выполняет сетевые запросы,
не использует внешние API и не требует ключей доступа.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# -----------------------------------------------------------------------------
# Константы
# -----------------------------------------------------------------------------

VALID_BASES = {"A", "C", "G", "T"}

HEADER = [
    "#",
    "Позиция (р. мтДНК)",
    "Ген",
    "Замена",
    "Тип гена",
    "Роль в психиатрии",
    "Популяц. частота (оценка)",
    "Функц. предиктор (рекомендация)",
    "Критерии ACMG/AMP (предварит.)",
    "Класс (предварит.)",
]


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------


@dataclass
class Snp:
    sample_id: str
    position: int
    ref: str
    alt: str


@dataclass
class QcInfo:
    sample_id: str
    haplogroup: str = ""
    private_alleles: Set[str] = field(default_factory=set)
    warnings: List[str] = field(default_factory=list)


@dataclass
class Config:
    reference_length: int
    gene_intervals: List[Tuple[int, int, str]]
    gene_type_rules: Dict[str, str]
    role_rules: Dict[str, str]
    predictor_rules: Dict[str, str]
    acmg_rules: Dict[str, str]
    frequency_rules: Dict[str, str]
    include_ref_alt_by_default: bool
    class_default: str


# -----------------------------------------------------------------------------
# Загрузка конфигурации
# -----------------------------------------------------------------------------


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Файл конфигурации не найден: {path}")

    with path.open("r", encoding="utf-8-sig") as fh:
        raw = json.load(fh)

    gene_intervals = []
    for item in raw["gene_intervals"]:
        start, end, gene = item
        gene_intervals.append((int(start), int(end), gene))

    return Config(
        reference_length=int(raw["reference"]["length"]),
        gene_intervals=gene_intervals,
        gene_type_rules=raw["gene_type_rules"],
        role_rules=raw["role_rules"],
        predictor_rules=raw["predictor_rules"],
        acmg_rules=raw["acmg_rules"],
        frequency_rules=raw["frequency_rules"],
        include_ref_alt_by_default=raw["output"].get(
            "include_ref_alt_by_default", False
        ),
        class_default=raw["output"].get("class_default", "VUS"),
    )


# -----------------------------------------------------------------------------
# Чтение TSV
# -----------------------------------------------------------------------------


def read_tsv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    rows: List[Dict[str, str]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t", quotechar='"')

        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            return rows

        for raw in reader:
            if not raw or all(not cell.strip() for cell in raw):
                continue

            while len(raw) < len(header):
                raw.append("")

            row = {header[i]: raw[i].strip() for i in range(len(header))}
            rows.append(row)

    return rows


# -----------------------------------------------------------------------------
# Парсинх входных файлов
# -----------------------------------------------------------------------------


def parse_snps(path: Path, include_ref_alt: bool) -> List[Snp]:
    rows = read_tsv(path)

    required = {"SampleID", "Position", "Ref", "Alt"}
    if rows and not required.issubset(rows[0].keys()):
        raise ValueError(
            "В файле вариантов ожидаются колонки: " + ", ".join(sorted(required))
        )

    snps: List[Snp] = []

    for line_no, row in enumerate(rows, start=2):
        sample_id = row.get("SampleID", "").strip()
        position_raw = row.get("Position", "").strip()
        ref = row.get("Ref", "").strip().upper()
        alt = row.get("Alt", "").strip().upper()

        if not sample_id:
            print(f"Warning: строка {line_no}: пустой SampleID.", file=sys.stderr)
            continue

        try:
            position = int(position_raw)
        except ValueError:
            print(
                f"Warning: строка {line_no}: некорректная позиция '{position_raw}'.",
                file=sys.stderr,
            )
            continue

        if len(ref) != 1 or len(alt) != 1 or ref not in VALID_BASES or alt not in VALID_BASES:
            print(
                f"Warning: строка {line_no}: некорректные аллели Ref='{ref}', Alt='{alt}'.",
                file=sys.stderr,
            )
            continue

        if not include_ref_alt and ref == alt:
            continue

        snps.append(Snp(sample_id=sample_id, position=position, ref=ref, alt=alt))

    return snps


def parse_qc(path: Path) -> Dict[str, QcInfo]:
    rows = read_tsv(path)

    required = {"SampleID", "Global Private Mutations"}
    if rows and not required.issubset(rows[0].keys()):
        raise ValueError(
            "В файле QC ожидаются как минимум колонки: " + ", ".join(sorted(required))
        )

    qc_map: Dict[str, QcInfo] = {}
    private_regex = re.compile(r"\b(\d+)([ACGTacgt])\b")

    for row in rows:
        sample_id = row.get("SampleID", "").strip()
        if not sample_id:
            continue

        info = qc_map.setdefault(sample_id, QcInfo(sample_id=sample_id))

        haplogroup = row.get("Haplogroup", "").strip()
        if haplogroup and not info.haplogroup:
            info.haplogroup = haplogroup

        private_field = row.get("Global Private Mutations", "")
        for match in private_regex.finditer(private_field):
            pos = int(match.group(1))
            base = match.group(2).upper()
            info.private_alleles.add(f"{pos}{base}")

        qtype = row.get("Type", "").strip().lower()
        message = row.get("Message", "").strip()
        if qtype in {"error", "warning"} and message:
            info.warnings.append(f"{qtype}: {message}")

    return qc_map


# -----------------------------------------------------------------------------
# Аннотация по конфигурации
# -----------------------------------------------------------------------------


def match_rule(rules: Dict[str, str], gene: str) -> Optional[str]:
    """
    Ищет правило в конфигурации:
      - точное совпадение имени гена;
      - префиксное совпадение, если ключ начинается с 'prefix:';
      - 'default', если задан.
    """
    if gene in rules:
        return rules[gene]

    for key, value in rules.items():
        if key.startswith("prefix:"):
            prefix = key[len("prefix:"):]
            if gene.startswith(prefix):
                return value

    return rules.get("default")


def assign_gene(position: int, config: Config) -> str:
    for start, end, gene in config.gene_intervals:
        if start <= position <= end:
            return gene
    return "не определено"


def make_record(
    index: int,
    snp: Snp,
    qc_info: Optional[QcInfo],
    config: Config,
) -> List[str]:
    gene = assign_gene(snp.position, config)
    substitution = f"{snp.ref}→{snp.alt}"

    gene_type = match_rule(config.gene_type_rules, gene) or "Не определено"
    role = match_rule(config.role_rules, gene) or "Не определено"
    predictor = match_rule(config.predictor_rules, gene) or "Требуется подбор"

    private_token = f"{snp.position}{snp.alt}"
    qc_private = bool(qc_info and private_token in qc_info.private_alleles)

    if qc_private:
        frequency = config.frequency_rules.get("private_label", "Приватная")
    else:
        frequency = config.frequency_rules.get(
            "unverified_label",
            "Не подтверждено; требуется проверка в gnomAD/1000 Genomes/MITOMAP",
        )

    rare_confirmed = qc_private or frequency.startswith("Приватная")

    if rare_confirmed:
        acmg = match_rule(config.acmg_rules, gene) or "PM2"
    else:
        acmg = "PM2 (требует подтверждения); требуется верификация частоты"

    variant_class = config.class_default

    return [
        str(index),
        str(snp.position),
        gene,
        substitution,
        gene_type,
        role,
        frequency,
        predictor,
        acmg,
        variant_class,
    ]


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def process_sample(
    sample_id: str,
    snps: List[Snp],
    qc_map: Dict[str, QcInfo],
    config: Config,
    out_dir: Path,
) -> None:
    sample_snps = [snp for snp in snps if snp.sample_id == sample_id]
    if not sample_snps:
        print(f"Warning: для {sample_id} не найдено вариантов.", file=sys.stderr)
        return

    sample_snps.sort(key=lambda x: x.position)

    qc_info = qc_map.get(sample_id)
    if qc_info is None:
        print(
            f"Warning: SampleID={sample_id} не найден в QC-файле. "
            "Приватные мутации не будут помечаться из QC.",
            file=sys.stderr,
        )
        qc_info = QcInfo(sample_id=sample_id)

    records = [
        make_record(idx + 1, snp, qc_info, config)
        for idx, snp in enumerate(sample_snps)
    ]

    out_file = out_dir / f"{sample_id}_from_AMP.csv"
    with out_file.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADER)
        writer.writerows(records)

    print(
        f"OK: sample={sample_id}, haplogroup={qc_info.haplogroup or 'не определён'}, "
        f"rows={len(records)}, out={out_file}",
        file=sys.stderr,
    )

    if qc_info.warnings:
        print(
            f"  QC notes: обнаружено {len(qc_info.warnings)} error/warning сообщений.",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Формирует таблицы в стиле from_AMP.csv по методологии AMP."
    )
    parser.add_argument("snps_file", type=Path, help="Путь к файлу вариантов (TSV)")
    parser.add_argument("qc_file", type=Path, help="Путь к файлу QC (TSV)")
    parser.add_argument("config_file", type=Path, help="Путь к amp_config.json")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("output"),
        help="Директория для выходных CSV (по умолчанию ./output)",
    )
    parser.add_argument(
        "--sample",
        default=None,
        help="Обработать только один SampleID. Если не указан — обрабатываются все.",
    )
    parser.add_argument(
        "--include-ref-alt",
        action="store_true",
        help="Оставлять строки, где Ref == Alt.",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.config_file)
        snps = parse_snps(
            args.snps_file,
            include_ref_alt=args.include_ref_alt or config.include_ref_alt_by_default,
        )
        qc_map = parse_qc(args.qc_file)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not snps:
        print("ERROR: после фильтрации не осталось вариантов.", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)

    samples = sorted({snp.sample_id for snp in snps})

    if args.sample:
        if args.sample not in samples:
            print(
                f"ERROR: SampleID={args.sample} не найден в файле вариантов.",
                file=sys.stderr,
            )
            return 2
        samples = [args.sample]

    for sample_id in samples:
        process_sample(sample_id, snps, qc_map, config, args.out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
