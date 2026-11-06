"""Stage timing, process RSS sampling (including native IfcOpenShell allocations), and counters."""
from __future__ import annotations
import csv
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

try:
    import psutil
except ImportError:
    psutil = None

class PerformanceLog:
    def __init__(self, notify=print, label='run'):
        self.notify = notify
        self.label = label
        self.started = perf_counter()
        self.records = []
        self._counters = {}
        self._process = psutil.Process(os.getpid()) if psutil else None
        self._stop = threading.Event()
        self._peak = 0
        self._sample_thread = None
        if self._process:
            self._sample_thread = threading.Thread(target=self._sample, daemon=True)
            self._sample_thread.start()

    def _rss(self):
        if self._process:
            try:
                return self._process.memory_info().rss
            except (OSError, psutil.Error):
                pass
        return 0

    def _sample(self):
        while not self._stop.wait(0.15):
            self._peak = max(self._peak, self._rss())

    def count(self, key, value):
        self._counters[key] = value

    @contextmanager
    def stage(self, label):
        start = perf_counter()
        before = self._rss()
        self.notify(f'>>> {label}...')
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            after = self._rss()
            self._peak = max(self._peak, before, after)
            self.records.append((label, elapsed, before, after, self._peak))
            self.notify(f'<<< {label}: {elapsed:.2f} s | RSS {after/2**20:.1f} MiB')

    def stop_sampling(self):
        """Idempotently stop the sampler, including on early exceptions."""
        self._stop.set()
        if self._sample_thread and self._sample_thread.is_alive():
            self._sample_thread.join(timeout=1)

    def finish(self, filename=None):
        self.stop_sampling()
        self._peak = max(self._peak, self._rss())
        total = perf_counter() - self.started
        if filename is None:
            self.notify(f'Elapsed total: {total:.2f} s')
            return {'elapsed_seconds': total, 'peak_rss_mib': self._peak/2**20, **self._counters}
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            writer.writerow(['engine','stage','duration_seconds','rss_before_mib','rss_after_mib','peak_rss_mib'])
            for name, duration, start, end, peak in self.records:
                writer.writerow([self.label,name,f'{duration:.4f}',f'{start/2**20:.2f}',f'{end/2**20:.2f}',f'{peak/2**20:.2f}'])
            writer.writerow([self.label,'TOTAL elapsed',f'{total:.4f}','','',f'{self._peak/2**20:.2f}'])
        with path.with_suffix('.metrics.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['metric','value'])
            for name, value in sorted(self._counters.items()):
                writer.writerow([name, value])
        self.notify(f'Elapsed total: {total:.2f} s | Timing: {path}')
        return {'elapsed_seconds': total, 'peak_rss_mib': self._peak/2**20, 'timing_csv': str(path), **self._counters}

    def save(self, filename):
        return self.finish(filename)
