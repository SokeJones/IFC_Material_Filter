"""Fast conservative IFC STEP file record pruning.

IfcOpenShell first writes the edited model to STEP; this module streams the
serialization and discards unwanted entity records without individually
calling model.remove() millions of times.

The keep-ID set MUST be a forward-closed entity graph. This module only
prunes STEP records; it does not rewrite IFC relationships or infer semantics.
"""
from __future__ import annotations

import os
import re
import json
import csv
from collections import Counter
from pathlib import Path

RECORD_START = re.compile(rb'^\s*#([0-9]+)\s*=\s*([A-Za-z0-9_]+)\s*\(')


def prune_serialized_ifc(source: Path, destination: Path, keep_ids: set[int],
                         notify=print, report_every_bytes: int = 64 * 1024 * 1024,
                         class_report: Path | None = None) -> dict:
    """Copy non-entity text and keep only entity records whose STEP ID is retained.

    Expects the standard IfcOpenShell serialization: STEP entities start at
    the beginning of a line, and each record ends in a semicolon. Multiline
    records are supported. It rejects unexpected record starts before a prior
    record is complete and refuses to silently ignore malformed endings.
    """
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Source and destination must differ')
    if destination.exists():
        raise FileExistsError(f'Pruned STEP destination already exists: {destination}')
    if not keep_ids:
        raise ValueError('No STEP entity IDs were selected')
    if any(not isinstance(eid, int) or eid <= 0 for eid in keep_ids):
        raise ValueError('Reachability contains non-serialized or invalid STEP IDs (e.g. #0)')
    written = 0
    skipped = 0
    found_keep_ids = set()
    duplicate_ids = set()
    all_seen_ids = set()
    read_bytes = 0
    checkpoint = report_every_bytes
    current_id = None
    current_keep = False
    pending = []
    class_kept = Counter()
    class_removed = Counter()
    bytes_kept = Counter()
    bytes_removed = Counter()
    current_class = None
    record_bytes = 0
    # We recognize records with one entity starting per line, the representation
    # produced by ifcopenshell.file.write(). Strings may contain semicolons but
    # the *last* non-whitespace character of a complete record is the terminator.
    def finished(line):
        return line.rstrip().endswith(b';')
    try:
        with source.open('rb') as inp, destination.open('xb') as out:
            for line in inp:
                read_bytes += len(line)
                match = RECORD_START.match(line)
                if match:
                    if current_id is not None:
                        raise ValueError(f'Unexpected STEP record start while #{current_id} is incomplete')
                    current_id = int(match.group(1))
                    current_class = match.group(2).decode('ascii', 'replace').upper()
                    record_bytes = 0
                    if current_id in all_seen_ids:
                        duplicate_ids.add(current_id)
                    all_seen_ids.add(current_id)
                    current_keep = current_id in keep_ids
                    pending = []
                if current_id is not None:
                    record_bytes += len(line)
                    if current_keep:
                        pending.append(line)
                    if finished(line):
                        if current_keep:
                            out.writelines(pending)
                            written += 1
                            found_keep_ids.add(current_id)
                            class_kept[current_class] += 1
                            bytes_kept[current_class] += record_bytes
                        else:
                            skipped += 1
                            class_removed[current_class] += 1
                            bytes_removed[current_class] += record_bytes
                        current_id = None
                        pending = []
                else:
                    out.write(line)
                if read_bytes >= checkpoint:
                    notify(f'STEP prune scanned {read_bytes / 2**20:,.0f} MiB; '
                           f'kept {written:,} entities, skipped {skipped:,}')
                    checkpoint += report_every_bytes
            if current_id is not None:
                raise ValueError(f'Truncated STEP record #{current_id}')
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    missing_ids = sorted(keep_ids - found_keep_ids)
    if missing_ids or duplicate_ids:
        # The diagnostics report survives, but an incomplete IFC is never published.
        diagnostics = {
            'expected_keep_records': len(keep_ids),
            'written_records': written,
            'missing_ids_count': len(missing_ids),
            'missing_ids': missing_ids[:100],
            'duplicate_step_ids_count': len(duplicate_ids),
            'duplicate_step_ids': sorted(duplicate_ids)[:100],
            'serialized_total_step_ids': len(all_seen_ids),
            'source': str(source),
        }
        diagnostic_path = destination.with_suffix('.step_prune_diagnostics.json')
        diagnostic_path.write_text(json.dumps(diagnostics, indent=2), encoding='utf-8')
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            f'STEP prune mismatch: expected {len(keep_ids):,} kept records, '
            f'wrote {written:,}; missing STEP IDs: {missing_ids[:20]}; '
            f'duplicates: {sorted(duplicate_ids)[:10]}. '
            f'Diagnostics: {diagnostic_path}. Refusing output.')
    if class_report is not None:
        report = Path(class_report)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['ifc_class', 'retained_records', 'retained_bytes',
                             'pruned_records', 'pruned_bytes', 'retained_bytes_pct_in_class'])
            classes = set(class_kept) | set(class_removed)
            for cls in sorted(classes, key=lambda c: bytes_kept[c], reverse=True):
                total = bytes_kept[cls] + bytes_removed[cls]
                writer.writerow([cls, class_kept[cls], bytes_kept[cls],
                                 class_removed[cls], bytes_removed[cls],
                                 f'{100 * bytes_kept[cls] / total:.2f}' if total else ''])
        notify(f'STEP retained/pruned bytes by IFC class: {report}')
    return {'records_kept': written, 'records_removed': skipped,
            'input_bytes': read_bytes, 'output_bytes': destination.stat().st_size}
