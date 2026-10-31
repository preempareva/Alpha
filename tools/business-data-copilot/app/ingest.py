"""Bounded CSV/XLSX parsing and upload profiling; formulas are kept as text."""

from __future__ import annotations

import csv
import io
import math
import os
import re
import unicodedata
import zipfile
from pathlib import PurePath
from typing import Any

import numpy as np
import openpyxl
import pandas as pd

from .models import ColumnProfile, ColumnRole, ColumnType, QualityWarning

MAX_UPLOAD_BYTES = int(os.getenv("COPILOT_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
if not 1 <= MAX_UPLOAD_BYTES <= 50 * 1024 * 1024:
    raise RuntimeError("COPILOT_MAX_UPLOAD_BYTES must be between 1 byte and 50 MB.")
MAX_ROWS = 50_000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 10_000
MAX_XLSX_EXPANDED_BYTES = 50 * 1024 * 1024


class UploadRejected(ValueError):
    """Raised when an upload is unsafe, malformed, or outside resource limits."""


def safe_extension(filename: str) -> str:
    if (not filename or filename != filename.strip() or "\x00" in filename
            or "/" in filename or "\\" in filename or PurePath(filename).name != filename):
        raise UploadRejected("Use a plain .csv or .xlsx filename without directory components.")
    normalized = unicodedata.normalize("NFC", filename)
    if normalized != filename or len(filename) > 180:
        raise UploadRejected("The uploaded filename is not in a supported normalized form.")
    extension = PurePath(filename).suffix.casefold()
    if extension not in {".csv", ".xlsx"}:
        raise UploadRejected("Only CSV and XLSX files are supported.")
    return extension


def parse_upload(filename: str, content: bytes) -> pd.DataFrame:
    extension = safe_extension(filename)
    if not content:
        raise UploadRejected("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        maximum_mib = MAX_UPLOAD_BYTES / (1024 * 1024)
        raise UploadRejected(f"Uploads are limited to {maximum_mib:g} MiB.")
    if extension == ".csv":
        frame = _parse_csv(content)
    else:
        frame = _parse_xlsx(content)
    if frame.empty:
        raise UploadRejected("The uploaded file has no data rows.")
    if len(frame) > MAX_ROWS:
        raise UploadRejected("The file exceeds the 50,000-row limit.")
    if not 1 <= len(frame.columns) <= MAX_COLUMNS:
        raise UploadRejected("The file must contain 1 to 100 columns.")
    if any(len(str(column)) > 120 for column in frame.columns):
        raise UploadRejected("Column names must be 120 characters or fewer.")
    if frame.columns.has_duplicates:
        raise UploadRejected("Column names must be unique.")
    if any(frame[column].map(lambda value: isinstance(value, str) and len(value) > MAX_CELL_CHARS).any()
           for column in frame.columns):
        raise UploadRejected("A cell exceeds the 10,000-character limit.")
    if any(not str(column).strip() for column in frame.columns):
        raise UploadRejected("Column names cannot be blank.")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def _parse_csv(content: bytes) -> pd.DataFrame:
    if b"\x00" in content:
        raise UploadRejected("CSV must be a text file using UTF-8 or Windows-1252 encoding.")
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise UploadRejected("CSV encoding is unsupported. Save it as UTF-8 and retry.")
    sample = text[:65_536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    try:
        header = next(csv.reader(io.StringIO(text[:65_536]), delimiter=delimiter))
    except (csv.Error, StopIteration) as exc:
        raise UploadRejected("CSV header could not be read.") from exc
    if not 1 <= len(header) <= MAX_COLUMNS:
        raise UploadRejected("The CSV must contain 1 to 100 columns.")
    if len({str(value).strip() for value in header}) != len(header):
        raise UploadRejected("CSV column names must be unique.")
    try:
        frame = pd.read_csv(
            io.StringIO(text), sep=delimiter, nrows=MAX_ROWS + 1, dtype="string",
            keep_default_na=True, on_bad_lines="error", encoding_errors="strict",
        )
    except (pd.errors.ParserError, UnicodeError, ValueError) as exc:
        raise UploadRejected("CSV rows are inconsistent or malformed.") from exc
    return frame


def _parse_xlsx(content: bytes) -> pd.DataFrame:
    source = io.BytesIO(content)
    if not zipfile.is_zipfile(source):
        raise UploadRejected("XLSX content is not a valid ZIP-based workbook.")
    source.seek(0)
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            normalized_names = [item.filename.replace("\\", "/").casefold() for item in members]
            names = set(normalized_names)
            if len(names) != len(members):
                raise UploadRejected("The workbook contains duplicate ZIP member paths.")
            required = {"[content_types].xml", "xl/workbook.xml"}
            if not required.issubset(names) or not any(
                name.startswith("xl/worksheets/sheet") and name.endswith(".xml") for name in names
            ):
                raise UploadRejected("The ZIP file is not a supported XLSX workbook.")
            if len(members) > 250 or sum(item.file_size for item in members) > MAX_XLSX_EXPANDED_BYTES:
                raise UploadRejected("The workbook expands beyond the safe XLSX size limit.")
            if any(item.file_size > max(item.compress_size * 200, 1024 * 1024) for item in members):
                raise UploadRejected("The workbook contains a highly compressed unsafe member.")
            if any(
                name.startswith("/") or re.match(r"^[a-z]:", name) is not None
                or any(part == ".." for part in name.split("/"))
                for name in names
            ):
                raise UploadRejected("The workbook contains an unsafe ZIP member path.")
            forbidden = ("vbaproject", "externallinks/", "embeddings/", "activex/", "oleobjects/")
            if any(any(marker in name for marker in forbidden) for name in names):
                raise UploadRejected("Macro-enabled workbooks, external links, and embedded objects are rejected.")
    except zipfile.BadZipFile as exc:
        raise UploadRejected("The XLSX container is damaged.") from exc

    source.seek(0)
    try:
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=False, keep_links=False)
        sheet = workbook.active
        if sheet is None:
            raise UploadRejected("The workbook has no active worksheet.")
        iterator = sheet.iter_rows(values_only=True)
        header_values = next(iterator, None)
        if not header_values:
            raise UploadRejected("The workbook's active worksheet is empty.")
        header = [str(value).strip() if value is not None else "" for value in header_values]
        if not 1 <= len(header) <= MAX_COLUMNS or any(not value for value in header):
            raise UploadRejected("The active worksheet must have 1 to 100 named columns.")
        if len(set(header)) != len(header):
            raise UploadRejected("Worksheet column names must be unique.")
        rows: list[tuple[Any, ...]] = []
        for row in iterator:
            if len(rows) >= MAX_ROWS:
                raise UploadRejected("The worksheet exceeds the 50,000-row limit.")
            if len(row) > MAX_COLUMNS:
                raise UploadRejected("The worksheet exceeds the 100-column limit.")
            rows.append(tuple(row[:MAX_COLUMNS]))
        workbook.close()
    except UploadRejected:
        raise
    except (OSError, ValueError, KeyError, StopIteration, zipfile.BadZipFile) as exc:
        raise UploadRejected("The active worksheet could not be safely read.") from exc
    return pd.DataFrame(rows, columns=header)


def profile_frame(frame: pd.DataFrame) -> tuple[list[ColumnProfile], list[QualityWarning], int]:
    duplicate_rows = int(frame.duplicated().sum())
    warnings: list[QualityWarning] = []
    profiles: list[ColumnProfile] = []
    if duplicate_rows:
        warnings.append(QualityWarning(
            severity="warning", code="duplicate_rows", message=f"Found {duplicate_rows} duplicate rows.",
        ))

    for name in frame.columns:
        series = frame[name]
        non_null = series.dropna()
        inferred, converted, invalid_count = _infer_series(non_null)
        cardinality = int(non_null.nunique(dropna=True))
        minimum: Any = None
        maximum: Any = None
        outliers = 0
        if not converted.empty:
            try:
                minimum = _json_scalar(converted.min())
                maximum = _json_scalar(converted.max())
            except (TypeError, ValueError):
                minimum = None
                maximum = None
        if inferred in {"integer", "number"} and not converted.empty:
            values = pd.to_numeric(converted, errors="coerce").dropna()
            if len(values):
                lower = float(values.quantile(0.25))
                upper = float(values.quantile(0.75))
                span = upper - lower
                outliers = int(((values < lower - 1.5 * span) | (values > upper + 1.5 * span)).sum())

        null_count = int(series.isna().sum())
        role: ColumnRole = "date" if inferred == "date" else "measure" if inferred in {"integer", "number"} else "dimension"
        profiles.append(ColumnProfile(
            name=str(name), inferred_type=inferred, null_count=null_count, invalid_count=invalid_count,
            cardinality=cardinality, minimum=minimum, maximum=maximum,
            outlier_count=outliers, suggested_role=role,
        ))
        if null_count:
            warnings.append(QualityWarning(
                severity="warning", code="null_values", column=str(name),
                message=f"{null_count} rows have no value for this column.",
            ))
        if invalid_count:
            warnings.append(QualityWarning(
                severity="high", code="invalid_values", column=str(name),
                message=f"{invalid_count} non-empty values do not match the inferred {inferred} type.",
            ))
        if outliers:
            warnings.append(QualityWarning(
                severity="info", code="iqr_outliers", column=str(name),
                message=f"{outliers} values fall outside the 1.5×IQR screening range.",
            ))
        if inferred in {"integer", "number"} and not converted.empty:
            if (pd.to_numeric(converted, errors="coerce") < 0).any():
                warnings.append(QualityWarning(
                    severity="warning", code="negative_numeric", column=str(name),
                    message="Negative numeric values are present; review whether they are valid for this field.",
                ))
    return profiles, warnings, duplicate_rows


def _infer_series(series: pd.Series) -> tuple[ColumnType, pd.Series, int]:
    if series.empty:
        return "text", series, 0
    strings = series.astype("string").str.strip()
    non_empty = strings[strings.ne("") & strings.notna()]
    if non_empty.empty:
        return "text", series.iloc[:0], 0
    lower = set(non_empty.str.casefold().unique())
    if lower.issubset({"true", "false", "yes", "no", "0", "1"}):
        bool_values = strings.str.casefold().map({"true": True, "yes": True, "1": True,
                                                 "false": False, "no": False, "0": False})
        return "boolean", bool_values, int(bool_values.isna().sum())
    numeric = pd.to_numeric(non_empty, errors="coerce")
    numeric_ratio = float(numeric.notna().mean())
    if numeric_ratio >= 0.9:
        valid = numeric.dropna()
        whole = bool(len(valid) == 0 or np.equal(np.mod(valid.astype(float), 1), 0).all())
        return ("integer" if whole else "number"), numeric, int(numeric.isna().sum())
    dates = pd.to_datetime(non_empty, errors="coerce", format="mixed", utc=True)
    date_ratio = float(dates.notna().mean()) if len(dates) else 0.0
    if date_ratio >= 0.9:
        return "date", dates, int(dates.isna().sum())
    return "text", strings, 0


def preview_rows(frame: pd.DataFrame, *, limit: int = 20) -> list[dict[str, Any]]:
    return [
        {str(key): _json_scalar(value) for key, value in row.items()}
        for row in frame.head(limit).to_dict(orient="records")
    ]


def _json_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)

