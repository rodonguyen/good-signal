"""
Parquet-based DataFrame cache for backtesting artifacts.

Use cases:
- resampled OHLCV (1m -> 1h)
- derived bars (daily crypto 24h periods)
- indicator frames (ATR series, breakout levels, etc.)

Design goals:
- deterministic filenames
- safe invalidation when upstream inputs change
- minimal coupling (cache is generic; callers define keys + dependencies)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd


def _safe_slug(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "x"


@dataclass(frozen=True)
class FileDependency:
    path: str
    size: int
    mtime_ns: int

    @staticmethod
    def from_path(path: str | Path) -> "FileDependency":
        p = Path(path)
        st = p.stat()
        return FileDependency(path=str(p), size=int(st.st_size), mtime_ns=int(st.st_mtime_ns))


@dataclass(frozen=True)
class CacheKey:
    """
    A stable identifier for a cached artifact.

    - namespace: top-level group, e.g. \"resample\"
    - symbol: e.g. \"ETHUSDT\"
    - artifact: e.g. \"1m_to_1h\"
    - params: any extra inputs that affect output (must be JSON-serializable)
    - version: bump when logic changes to force invalidation
    """

    namespace: str
    symbol: str
    artifact: str
    params: Mapping[str, Any]
    version: str = "v1"

    def to_slug(self) -> str:
        parts = [
            _safe_slug(self.symbol),
            _safe_slug(self.artifact),
            _safe_slug(self.version),
        ]
        return "__".join(parts)


class ParquetDataFrameCache:
    """
    Cache DataFrames as Parquet with a JSON sidecar metadata file.

    The sidecar tracks:
    - cache key (namespace/symbol/artifact/params/version)
    - dependency fingerprints (file size + mtime_ns)
    """

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _paths(self, key: CacheKey) -> tuple[Path, Path]:
        ns_dir = self.base_dir / _safe_slug(key.namespace)
        ns_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = ns_dir / f"{key.to_slug()}.parquet"
        meta_path = ns_dir / f"{key.to_slug()}.meta.json"
        return parquet_path, meta_path

    def _meta_matches(self, meta: Mapping[str, Any], deps: Sequence[FileDependency]) -> bool:
        cached_deps = meta.get("dependencies", [])
        if len(cached_deps) != len(deps):
            return False
        for expected, actual in zip(cached_deps, deps, strict=False):
            if str(expected.get("path")) != actual.path:
                return False
            if int(expected.get("size", -1)) != actual.size:
                return False
            if int(expected.get("mtime_ns", -1)) != actual.mtime_ns:
                return False
        return True

    def get(self, key: CacheKey, *, dependencies: Sequence[FileDependency]) -> pd.DataFrame | None:
        parquet_path, meta_path = self._paths(key)
        if not parquet_path.exists() or not meta_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        # Key check (defensive)
        if meta.get("version") != key.version:
            return None
        if meta.get("namespace") != key.namespace or meta.get("symbol") != key.symbol or meta.get("artifact") != key.artifact:
            return None
        if meta.get("params") != dict(key.params):
            return None

        if not self._meta_matches(meta, dependencies):
            return None

        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            return None

    def set(self, key: CacheKey, *, dependencies: Sequence[FileDependency], df: pd.DataFrame) -> None:
        parquet_path, meta_path = self._paths(key)

        # Write parquet
        df.to_parquet(parquet_path, index=False)

        meta = {
            "namespace": key.namespace,
            "symbol": key.symbol,
            "artifact": key.artifact,
            "params": dict(key.params),
            "version": key.version,
            "dependencies": [d.__dict__ for d in dependencies],
        }
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

    def get_or_compute(
        self,
        key: CacheKey,
        *,
        dependencies: Sequence[FileDependency],
        compute: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame:
        cached = self.get(key, dependencies=dependencies)
        if cached is not None:
            return cached
        df = compute()
        self.set(key, dependencies=dependencies, df=df)
        return df


