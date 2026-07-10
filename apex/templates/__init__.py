"""Template engine module.

This module provides template variable resolution for EPG generation.
Variables are substituted in title/description templates like:
    "{team_name} vs {opponent}" -> "Detroit Lions vs Chicago Bears"

Supports three suffix types:
    {var} - current game context
    {var.next} - next scheduled game
    {var.last} - last completed game
"""

from apex.templates.conditions import (
    ConditionalDescriptionSelector,
    ConditionEvaluator,
    ConditionOption,
    get_condition_selector,
)
from apex.templates.context import (
    GameContext,
    Odds,
    TeamChannelContext,
    TemplateContext,
)
from apex.templates.context_builder import (
    ContextBuilder,
    build_context_for_event,
)
from apex.templates.resolver import TemplateResolver, resolve
from apex.templates.variables import (
    Category,
    SuffixRules,
    VariableRegistry,
    get_registry,
)

__all__ = [
    # Conditional system
    "ConditionEvaluator",
    "ConditionOption",
    "ConditionalDescriptionSelector",
    "get_condition_selector",
    # Context builder
    "ContextBuilder",
    "build_context_for_event",
    # Context types
    "GameContext",
    "Odds",
    "TeamChannelContext",
    "TemplateContext",
    # Resolver
    "TemplateResolver",
    "resolve",
    # Registry
    "Category",
    "SuffixRules",
    "VariableRegistry",
    "get_registry",
]
