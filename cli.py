"""Command-line interface for IFC Material Filter.

Examples:
  python cli.py source.ifc filtered.ifc --material "Concrete;Steel"
  python cli.py source.ifc --dry-run --material "Concrete"
  python cli.py source.ifc filtered.ifc --material "Concrete" --save-reports
"""
import argparse
from pathlib import Path

from filter_engine import export_ifc


def build_parser():
    parser = argparse.ArgumentParser(description='Standalone IFC material filter')
    parser.add_argument('input', help='Source IFC model')
    parser.add_argument('output', nargs='?', help='Filtered IFC output path (optional in --dry-run)')
    parser.add_argument('--material', action='append', required=True,
                        help='Material name(s), separated by semicolons or newlines; may be repeated')
    parser.add_argument('--parent-mode', default='aggregates',
                        choices=['none', 'aggregates', 'aggregates+nests'])
    parser.add_argument('--dry-run', action='store_true', help='Write audit CSV only; do not export IFC')
    parser.add_argument('--engine', choices=['both', 'ifcpatch', 'batch'], default='batch')
    parser.add_argument('--validation', choices=['full', 'basic'], default='basic')
    audit_flags = parser.add_mutually_exclusive_group()
    audit_flags.add_argument('--save-audit', action='store_true',
                             help='Additionally save audit CSV (default: off)')
    audit_flags.add_argument('--no-audit', action='store_true',
                             help='Deprecated alias for default: do not save audit CSV')
    report_flags = parser.add_mutually_exclusive_group()
    report_flags.add_argument('--save-reports', action='store_true',
                              help='Additionally save timing/comparison/diagnostic reports')
    report_flags.add_argument('--no-reports', action='store_true',
                              help='Deprecated alias for default: do not save reports')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.output and not args.dry_run:
        parser.error('the output IFC path is required unless --dry-run is selected')
    output = args.output or str(Path(args.input).with_name(Path(args.input).stem + '_filtered.ifc'))
    return export_ifc(args.input, output, args.material, parent_mode=args.parent_mode,
                      dry_run=args.dry_run, engine=args.engine, validation=args.validation,
                      save_audit=args.save_audit, save_reports=args.save_reports)


if __name__ == '__main__':
    main()
