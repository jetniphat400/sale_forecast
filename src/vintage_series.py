"""The exact monthly series each forward-test vintage is fitted on, saved and hash-checked (METRICS.md Sec.27).

Vintages 1 and 2 cannot be reproduced because `output/data/processed_all_divisions_monthly_qty.csv` is overwritten each month.
From vintage 3 on, step 5 saves the bytes of that file as the vintage read them, gzip-compressed (mtime 0, so the same bytes give
the same file), under `output/forward_test/vintage_series/`, and records the SHA-256 of the uncompressed bytes in the vintage's
metadata (`fit_series_sha256`). Step 6 verifies every recorded hash before it scores. A file is never overwritten, and a vintage
without a recorded hash (vintages 1 and 2, written before this change) is reported as such, never as verified.
"""
import gzip
import hashlib
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES_DIR = os.path.join(PROJECT_ROOT, "output", "forward_test", "vintage_series")
SERIES_SOURCE = "output/data/processed_all_divisions_monthly_qty.csv"


class VintageSeriesError(Exception):
    """A saved fit series is missing, would be overwritten, or does not match the hash recorded in the vintage's metadata."""


def series_filename(vintage_id: int) -> str:
    return f"vintage_{int(vintage_id):03d}_fit_series.csv.gz"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def metadata_fields(series_bytes: bytes, vintage_id: int) -> dict:
    """The keys step 5 adds to the vintage's metadata entry."""
    return {"fit_series_file": f"output/forward_test/vintage_series/{series_filename(vintage_id)}",
            "fit_series_source": SERIES_SOURCE, "fit_series_sha256": sha256_hex(series_bytes),
            "fit_series_n_bytes": len(series_bytes), "fit_series_hash_basis": "sha256 of the uncompressed csv bytes"}


def save_series(series_bytes: bytes, vintage_id: int, directory: str = None) -> str:
    """Writes the compressed series for a vintage and returns its path; an existing file is never replaced."""
    directory = directory or SERIES_DIR
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, series_filename(vintage_id))
    if os.path.exists(path):
        raise VintageSeriesError(f"{path} already exists; a vintage's saved series is never overwritten")
    tmp = path + ".part"
    with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(series_bytes)
    os.replace(tmp, path)
    return path


def read_series(vintage_id: int, directory: str = None) -> bytes:
    path = os.path.join(directory or SERIES_DIR, series_filename(vintage_id))
    if not os.path.exists(path):
        raise VintageSeriesError(f"vintage {vintage_id}: the saved fit series {path} is missing")
    with gzip.open(path, "rb") as f:
        return f.read()


def verify_series(metadata: dict, directory: str = None) -> dict:
    """Checks every vintage whose metadata records `fit_series_sha256` against its saved file. Raises VintageSeriesError on a
    missing file or a different hash. Vintages without a recorded hash are listed under `no_series_saved`."""
    verified, no_series = [], []
    for key in sorted(metadata, key=lambda k: int(k)):
        expected = metadata[key].get("fit_series_sha256")
        if not expected:
            no_series.append(int(key))
            continue
        actual = sha256_hex(read_series(int(key), directory))
        if actual != expected:
            raise VintageSeriesError(f"vintage {key}: the saved fit series hashes to {actual}, the metadata records {expected}")
        verified.append(int(key))
    return {"verified": verified, "no_series_saved": no_series}
