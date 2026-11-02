#!/usr/bin/env python3
"""A dependency-free, configurable CSV cleaner."""

from __future__ import annotations

import argparse
import codecs
import csv
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence


EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_CONFIG = 2
EXIT_INPUT = 3
EXIT_OUTPUT = 4
AUTO_ENCODINGS = ("utf-8-sig", "gb18030")


class ConfigError(Exception):
    pass


class InputError(Exception):
    pass


class OutputError(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ConfigError(message)


def parser() -> ArgumentParser:
    result = ArgumentParser(description="Clean CSV data using configurable rules.")
    result.add_argument("--input", required=True, type=Path, help="input CSV path")
    result.add_argument("--output", required=True, type=Path, help="valid-row CSV path")
    result.add_argument(
        "--rejected",
        type=Path,
        help="rejected-row CSV path (default: rejected.csv beside output)",
    )
    result.add_argument(
        "--encoding",
        default="auto",
        help="input encoding, or 'auto' (tries UTF-8/UTF-8 BOM, then GB18030)",
    )
    result.add_argument(
        "--required", action="append", default=[], metavar="FIELDS",
        help="required field(s), comma separated; repeatable",
    )
    result.add_argument(
        "--unique", action="append", default=[], metavar="FIELDS",
        help="unique key field(s), comma separated; omitted means whole-row deduplication",
    )
    result.add_argument(
        "--integer", action="append", default=[], metavar="FIELDS",
        help="integer field(s), comma separated; repeatable",
    )
    result.add_argument(
        "--range", dest="ranges", action="append", default=[], metavar="FIELD:MIN:MAX",
        help="finite numeric range (inclusive); MIN or MAX may be empty; repeatable",
    )
    result.add_argument(
        "--name-field", action="append", default=[], metavar="FIELD",
        help="field using the demonstration name rule; repeatable",
    )
    return result


def split_fields(values: Iterable[str]) -> list[str]:
    fields: list[str] = []
    for value in values:
        for field in value.split(","):
            field = field.strip()
            if not field:
                raise ConfigError("field lists must not contain an empty field name")
            if field not in fields:
                fields.append(field)
    return fields


def parse_ranges(values: Iterable[str]) -> dict[str, tuple[float | None, float | None]]:
    result: dict[str, tuple[float | None, float | None]] = {}
    for value in values:
        parts = value.split(":")
        if len(parts) != 3 or not parts[0].strip():
            raise ConfigError(f"invalid range {value!r}; expected FIELD:MIN:MAX")
        field, lower_text, upper_text = (part.strip() for part in parts)
        try:
            lower = float(lower_text) if lower_text else None
            upper = float(upper_text) if upper_text else None
        except ValueError as exc:
            raise ConfigError(f"range bounds must be numeric: {value!r}") from exc
        if (lower is not None and not math.isfinite(lower)) or (
            upper is not None and not math.isfinite(upper)
        ):
            raise ConfigError(f"range bounds must be finite: {value!r}")
        if lower is None and upper is None:
            raise ConfigError(f"range must have at least one bound: {value!r}")
        if lower is not None and upper is not None and lower > upper:
            raise ConfigError(f"range minimum exceeds maximum: {value!r}")
        if field in result:
            raise ConfigError(f"duplicate range rule for field {field!r}")
        result[field] = (lower, upper)
    return result


def resolve_encoding(name: str) -> str:
    if name.lower() == "auto":
        return "auto"
    try:
        return codecs.lookup(name).name
    except LookupError as exc:
        raise ConfigError(f"unknown encoding: {name!r}") from exc


def read_text(path: Path, encoding: str) -> tuple[str, str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read input file {path}: {exc}") from exc

    candidates = AUTO_ENCODINGS if encoding == "auto" else (encoding,)
    errors: list[str] = []
    for candidate in candidates:
        try:
            return payload.decode(candidate), candidate
        except UnicodeDecodeError as exc:
            errors.append(f"{candidate}: {exc.reason}")
    raise InputError("unable to decode input; " + "; ".join(errors))


def read_csv(path: Path, encoding: str) -> tuple[list[str], list[dict[str, str]], str]:
    text, used_encoding = read_text(path, encoding)
    try:
        reader = csv.reader(text.splitlines(keepends=True), strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise InputError("input CSV is empty and has no header") from exc
        if not header or any(name == "" for name in header):
            raise InputError("CSV header contains an empty field name")
        if len(set(header)) != len(header):
            raise InputError("CSV header contains duplicate field names")

        rows: list[dict[str, str]] = []
        width = len(header)
        for line_number, values in enumerate(reader, start=2):
            if len(values) != width:
                raise InputError(
                    f"CSV row {line_number} has {len(values)} columns; expected {width}"
                )
            rows.append(dict(zip(header, values)))
    except csv.Error as exc:
        raise InputError(f"invalid CSV format: {exc}") from exc
    return header, rows, used_encoding


def valid_name(value: str) -> bool:
    """Demonstration rule: Unicode letters joined by single common separators."""
    separators = {" ", "-", "'", "’", "·"}
    if not value or value[0] in separators or value[-1] in separators:
        return False
    previous_separator = False
    for character in value:
        if character in separators:
            if previous_separator:
                return False
            previous_separator = True
        elif character.isalpha():
            previous_separator = False
        else:
            return False
    return True


def clean_rows(
    header: Sequence[str],
    rows: Iterable[dict[str, str]],
    required: Sequence[str],
    unique: Sequence[str],
    integers: Sequence[str],
    ranges: dict[str, tuple[float | None, float | None]],
    name_fields: Sequence[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    configured = set(required) | set(unique) | set(integers) | set(ranges) | set(name_fields)
    missing = sorted(configured - set(header))
    if missing:
        raise ConfigError("configured field(s) not found in header: " + ", ".join(missing))

    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()

    for original in rows:
        row = {field: original[field].strip() for field in header}
        reasons: list[str] = []

        for field in required:
            if row[field] == "":
                reasons.append(f"{field}: required value is missing")
        for field in integers:
            value = row[field]
            if value == "":
                reasons.append(f"{field}: integer value is missing")
            else:
                try:
                    int(value)
                except ValueError:
                    reasons.append(f"{field}: not an integer")
        for field, (lower, upper) in ranges.items():
            value = row[field]
            if value == "":
                reasons.append(f"{field}: numeric value is missing")
                continue
            try:
                number = float(value)
            except ValueError:
                reasons.append(f"{field}: not numeric")
                continue
            if not math.isfinite(number):
                reasons.append(f"{field}: value is not finite")
            elif lower is not None and number < lower:
                reasons.append(f"{field}: below minimum {lower:g}")
            elif upper is not None and number > upper:
                reasons.append(f"{field}: above maximum {upper:g}")
        for field in name_fields:
            if row[field] != "" and not valid_name(row[field]):
                reasons.append(f"{field}: invalid demonstration name format")

        if not reasons:
            key_fields = unique or list(header)
            key = tuple(row[field] for field in key_fields)
            if key in seen:
                reasons.append("duplicate key: " + ", ".join(key_fields))
            else:
                # Invalid rows deliberately never reserve a uniqueness key.
                seen.add(key)

        if reasons:
            rejected_row = {field: original[field] for field in header}
            rejected_row["error_reason"] = "; ".join(reasons)
            rejected.append(rejected_row)
        else:
            accepted.append(row)
    return accepted, rejected


def write_temp_csv(target: Path, header: Sequence[str], rows: Iterable[dict[str, str]]) -> Path:
    if not target.parent.is_dir():
        raise OutputError(f"output directory does not exist: {target.parent}")
    temp_path: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(header), extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        return temp_path
    except (OSError, csv.Error, ValueError) as exc:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise OutputError(f"cannot prepare output {target}: {exc}") from exc


def write_outputs(
    output: Path,
    rejected_path: Path,
    header: Sequence[str],
    accepted: list[dict[str, str]],
    rejected: list[dict[str, str]],
) -> None:
    output_temp: Path | None = None
    rejected_temp: Path | None = None
    try:
        output_temp = write_temp_csv(output, header, accepted)
        rejected_temp = write_temp_csv(
            rejected_path, [*header, "error_reason"], rejected
        )
        os.replace(output_temp, output)
        output_temp = None
        os.replace(rejected_temp, rejected_path)
        rejected_temp = None
    except OSError as exc:
        raise OutputError(f"cannot replace output file: {exc}") from exc
    finally:
        for temporary in (output_temp, rejected_temp):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def run(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    required = split_fields(args.required)
    unique = split_fields(args.unique)
    integers = split_fields(args.integer)
    name_fields = split_fields(args.name_field)
    ranges = parse_ranges(args.ranges)
    encoding = resolve_encoding(args.encoding)
    rejected_path = args.rejected or args.output.with_name("rejected.csv")

    input_path = canonical(args.input)
    output_path = canonical(args.output)
    rejected_path = canonical(rejected_path)
    if len({input_path, output_path, rejected_path}) != 3:
        raise ConfigError("input, output, and rejected paths must be different")

    header, rows, used_encoding = read_csv(input_path, encoding)
    accepted, rejected = clean_rows(
        header, rows, required, unique, integers, ranges, name_fields
    )
    write_outputs(output_path, rejected_path, header, accepted, rejected)
    print(
        f"encoding={used_encoding}; accepted={len(accepted)}; "
        f"rejected={len(rejected)}; output={output_path}; rejected_output={rejected_path}"
    )
    return EXIT_REJECTED if rejected else EXIT_OK


def main() -> int:
    try:
        return run()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except InputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except OutputError as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return EXIT_OUTPUT
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
