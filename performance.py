"""Per-run monotonic timing logs with an optional CSV sidecar."""
from __future__ import annotations

import csv
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter


class PerformanceLog:
    def __init__(self, notify=print):
        self.notify = notify
        self.started = perf_counter()
        self.records: list[tuple[str, float]] = []

    @contextmanager
    def stage(self, label: str):
        start = perf_counter()
        self.notify(f'>>> {label}...')
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self.records.append((label, elapsed))
            self.notify(f'<<< {label}: {elapsed:.2f} s')

    def save(self, filename: str | Path):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        total = perf_counter() - self.started
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['stage', 'duration_seconds'])
            for name, seconds in self.records:
                writer.writerow([name, f'{seconds:.4f}'])
            writer.writerow(['TOTAL elapsed', f'{total:.4f}'])
        self.notify(f'Elapsed total: {total:.2f} s | Performance CSV: {path}')
        return total
