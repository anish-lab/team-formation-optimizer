"""Safe CSV loading: the uploaded bytes are only ever parsed as text data, never executed or written to disk."""
from __future__ import annotations
import csv
import io
import pandas as pd
from werkzeug.utils import secure_filename

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "nil"}


class CsvError(Exception):
    def __init__(self, code: str, message: str, details=None):
        self.code, self.message, self.details = code, message, details
        super().__init__(message)


def is_missing(s) -> bool:
    return s is None or str(s).strip().lower() in MISSING_TOKENS


def read_csv_bytes(filename: str | None, data: bytes, max_bytes: int, max_rows: int = 5000) -> pd.DataFrame:
    name = secure_filename(filename or "")
    if not name.lower().endswith((".csv", ".txt")):
        raise CsvError("invalid_file_type", "Only .csv files are accepted.")
    if len(data) > max_bytes:
        raise CsvError("file_too_large", f"File exceeds the {max_bytes // 1024} KB limit.")
    if not data.strip():
        raise CsvError("empty_file", "The file is empty.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError("invalid_encoding", "File must be UTF-8 encoded text.")
    try:
        header = next(csv.reader(io.StringIO(text)))
    except Exception:
        raise CsvError("invalid_header", "Could not read a header row.")
    header = [h.strip() for h in header]
    if any(h == "" for h in header):
        raise CsvError("invalid_header", "Header contains empty column names.",
                       {"columns": [i + 1 for i, h in enumerate(header) if h == ""]})
    dups = sorted({h for h in header if header.count(h) > 1})
    if dups:
        raise CsvError("duplicate_columns", f"Duplicate column names: {', '.join(dups)}", {"columns": dups})
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_filter=False)
    except Exception:
        raise CsvError("malformed_csv", "The file could not be parsed as CSV (check delimiters and quoting).")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")
    if len(df) == 0:
        raise CsvError("no_rows", "The file has a header but no data rows.")
    if len(df) > max_rows:
        raise CsvError("too_many_rows", f"File has {len(df)} rows; the limit is {max_rows}.")
    return df
