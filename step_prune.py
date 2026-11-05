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
from pathlib import Path

RECORD_START = re.compile(rb'^\s*#([0-9]+)\s*=')


def prune_serialized_ifc(source: Path, destination: Path, keep_ids: set[int],
                         notify=print, report_every_bytes: int = 64 * 1024 * 1024) -> dict:
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
    written = 0
    skipped = 0
    read_bytes = 0
    checkpoint = report_every_bytes
    current_id = None
    current_keep = False
    pending = []
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
                    current_keep = current_id in keep_ids
                    pending = []
                if current_id is not None:
                    if current_keep:
                        pending.append(line)
                    if finished(line):
                        if current_keep:
                            out.writelines(pending)
                            written += 1
                        else:
                            skipped += 1
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
    if written != len(keep_ids):
        destination.unlink(missing_ok=True)
        raise RuntimeError(f'STEP prune expected {len(keep_ids):,} kept records, '
                           f'but wrote {written:,}; refusing output')
    return {'records_kept': written, 'records_removed': skipped,
            'input_bytes': read_bytes, 'output_bytes': destination.stat().st_size}
