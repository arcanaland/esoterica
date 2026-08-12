"""A shallow, dependency-free reading of the Tarot Esoterica Specification.

Downstream of ESOTERICA.md, not of this corpus: nothing here knows that
sources/mcelroy exists.
"""

from esoterica_spec.validate import Finding, Report, check

__all__ = ["Finding", "Report", "check"]
