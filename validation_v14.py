"""Structural validation of filtered IFCs; does not replace viewer geometry checks."""
import logging

class ErrorCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.errors = 0
        self.warnings = 0
        self.samples = []
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.errors += 1
            if len(self.samples) < 5:
                self.samples.append(record.getMessage()[:300])
        elif record.levelno >= logging.WARNING:
            self.warnings += 1


def full_validate(model, notify=print):
    """IfcOpenShell schema/attribute/cardinality checks, no expensive WHERE rules.

    Pre-existing source errors may survive filtering; report rather than silently
    pretending that a successful parse means a valid IFC.
    """
    import ifcopenshell.validate
    logger = logging.getLogger('ifc_material_filter_schema_validation')
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    handler = ErrorCounter()
    logger.addHandler(handler)
    try:
        ifcopenshell.validate.validate(model, logger, express_rules=False)
    finally:
        logger.removeHandler(handler)
    notify(f'IFC validation: {handler.errors} error(s), {handler.warnings} warning(s)')
    if handler.samples:
        notify('Sample schema findings: ' + ' | '.join(handler.samples[:2]))
    return {'schema_validation_errors': handler.errors,
            'schema_validation_warnings': handler.warnings,
            'schema_validation_examples': handler.samples,
            'express_where_rules_checked': False}
