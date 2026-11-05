"""Command-line alternative. Example:
python cli.py model.ifc output.ifc --material "Stahlbeton Schweiz" --material "Beton C30/37"
"""
import argparse
from filter_engine import export_ifc

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Standalone IFC material filter')
    parser.add_argument('input')
    parser.add_argument('output')
    parser.add_argument('--material', action='append', required=True, help='Repeat for multiple material names')
    parser.add_argument('--parent-mode', default='aggregates', choices=['none','aggregates','aggregates+nests'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--engine', choices=['both','ifcpatch','batch'], default='both')
    parser.add_argument('--validation', choices=['full','basic'], default='full')
    parser.add_argument('--no-audit', action='store_true', help='Do not save audit CSV unless --dry-run')
    parser.add_argument('--no-reports', action='store_true', help='Do not save timing/comparison/diagnostic reports')
    args = parser.parse_args()
    export_ifc(args.input, args.output, args.material, parent_mode=args.parent_mode, dry_run=args.dry_run,
               engine=args.engine, validation=args.validation,
               save_audit=not args.no_audit, save_reports=not args.no_reports)
