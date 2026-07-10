"""Template variables module.

Importing this module registers all template variables via decorators.
Each variable file defines extractors decorated with @register_variable.
"""

from apex.templates.variables import (  # noqa: F401 - side effect imports
    broadcast,
    combat,
    conference,
    home_away,
    identity,
    motorsports,
    odds,
    outcome,
    playoffs,
    rankings,
    records,
    scores,
    soccer,
    standings,
    statistics,
    streaks,
    summary,
    tennis,
    venue,
)
from apex.templates.variables import datetime as datetime_vars  # noqa: F401
from apex.templates.variables.registry import (
    Category,
    SuffixRules,
    TemplateScope,
    VariableDefinition,
    VariableRegistry,
    get_registry,
    register_variable,
)

__all__ = [
    "Category",
    "SuffixRules",
    "TemplateScope",
    "VariableDefinition",
    "VariableRegistry",
    "get_registry",
    "register_variable",
]
