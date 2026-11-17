class PermanentJobError(Exception):
    """A failure another attempt cannot fix (the report is gone, a template is missing...)."""

    # What the person who sent the report is told (a services/i18n.py key).
    reason_key = "failure"
