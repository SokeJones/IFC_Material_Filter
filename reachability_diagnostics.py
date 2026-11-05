"""Bounded-memory diagnostics for experimental batch reachability.

Only aggregate counters and bounded inverse-fanout samples are stored; never
retain one diagnostic record per IFC entity on very large models.
"""
from __future__ import annotations
from collections import Counter
import heapq
import json
from pathlib import Path


class ReachabilityDiagnostics:
    def __init__(self, enabled=True, top_n=30):
        self.enabled = enabled
        self.top_n = top_n
        self.ingress = Counter()
        self.seen_classes = Counter()
        self.inverse_source_classes = Counter()
        self.inverse_relationship_classes = Counter()
        self.inverse_candidates = Counter()
        self.inverse_expansions = Counter()
        self.root_classes = Counter()
        self._hubs = []
        self._serial = 0
        self.visited = 0
        self.transient = 0

    def root(self, entity):
        if self.enabled:
            self.root_classes[entity.is_a()] += 1

    def visited_entity(self, entity, inbound, source_class=''):
        if not self.enabled:
            return
        self.visited += 1
        cls = entity.is_a()
        self.seen_classes[cls] += 1
        self.ingress[inbound] += 1
        if inbound == 'inverse_relationship':
            self.inverse_relationship_classes[cls] += 1
            self.inverse_expansions[source_class] += 1

    def transient_entity(self):
        if self.enabled:
            self.transient += 1

    def inverse_traversal(self, source, number, by_class):
        if not self.enabled:
            return
        cls = source.is_a()
        self.inverse_source_classes[cls] += 1
        for relationship, count in by_class.items():
            self.inverse_candidates[relationship] += count
        if number <= 0:
            return
        self._serial += 1
        sample = (number, self._serial, {
            'source_step': source.id(),
            'source_class': cls,
            'source_globalid': getattr(source, 'GlobalId', None),
            'allowed_inverse_edges': number,
            'edge_classes': dict(by_class),
        })
        if len(self._hubs) < self.top_n:
            heapq.heappush(self._hubs, sample)
        elif sample[0] > self._hubs[0][0]:
            heapq.heapreplace(self._hubs, sample)

    def report(self):
        def sorted_count(counter):
            return [{'name': k, 'count': v} for k,v in counter.most_common()]
        return {
            'description': 'Diagnostics only: traversal semantics remain identical to v1.4.3.',
            'visited_serialized_entities': self.visited,
            'transient_inline_visits': self.transient,
            'root_classes': sorted_count(self.root_classes),
            'retained_entity_classes': sorted_count(self.seen_classes),
            'first_discovery_path': sorted_count(self.ingress),
            'inverse_traversal_source_classes': sorted_count(self.inverse_source_classes),
            'allowed_inverse_edge_classes': sorted_count(self.inverse_candidates),
            'newly_discovered_inverse_relationship_classes': sorted_count(self.inverse_relationship_classes),
            'inverse_expansion_source_classes': sorted_count(self.inverse_expansions),
            'largest_inverse_fanout_sources': [h[2] for h in sorted(self._hubs, reverse=True)],
            'interpretation_warning': ('A first-discovery path is not an exclusive causal dependency. '
                                      'A retained entity can be reachable by multiple paths.'),
        }

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.report(), indent=2, ensure_ascii=False), encoding='utf-8')
        return path
