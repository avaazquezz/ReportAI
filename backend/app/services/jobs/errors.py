class PermanentJobError(Exception):
    """A failure another attempt cannot fix (the report is gone, a template is missing...)."""
