"""Conditional action evaluation: determine if an action should execute."""

from __future__ import annotations

import platform
import re
from typing import Any

from playnite_py.models.action import ActionCondition, GameAction
from playnite_py.models.game import Game
from playnite_py.actions.variables import VariableResolver


class ConditionEvaluator:
    """Evaluates action conditions against game state and environment."""

    def __init__(self, variable_resolver: VariableResolver | None = None):
        self._resolver = variable_resolver or VariableResolver()

    def should_execute(
        self, action: GameAction, game: Game | None = None
    ) -> tuple[bool, str]:
        """Evaluate all conditions for an action.

        Returns (should_execute, reason). If all conditions pass,
        returns (True, ""). Otherwise returns (False, "reason").
        """
        if not action.enabled:
            return False, "Action is disabled"

        if not action.conditions:
            return True, ""

        context = self._resolver.build_context(game)

        for condition in action.conditions:
            passed, reason = self._evaluate_condition(condition, context)
            if not passed:
                return False, reason

        return True, ""

    def _evaluate_condition(
        self, condition: ActionCondition, context: dict[str, str]
    ) -> tuple[bool, str]:
        """Evaluate a single condition."""
        actual = context.get(condition.field, "")
        expected = condition.value
        op = condition.operator

        if op == "equals":
            if actual.lower() != expected.lower():
                return False, f"{condition.field} '{actual}' != '{expected}'"
        elif op == "not_equals":
            if actual.lower() == expected.lower():
                return False, f"{condition.field} '{actual}' == '{expected}'"
        elif op == "contains":
            if expected.lower() not in actual.lower():
                return False, f"{condition.field} does not contain '{expected}'"
        elif op == "not_contains":
            if expected.lower() in actual.lower():
                return False, f"{condition.field} contains '{expected}'"
        elif op == "matches":
            if len(expected) > 200:
                return False, "Regex pattern exceeds maximum length (200 characters)"
            try:
                pattern = re.compile(expected, re.IGNORECASE)
            except re.error as e:
                return False, f"Invalid regex pattern: {e}"
            if not pattern.search(actual):
                return False, f"{condition.field} does not match '{expected}'"
        elif op == "gt":
            if not self._numeric_compare(actual, expected, lambda a, b: a > b):
                return False, f"{condition.field} '{actual}' not > '{expected}'"
        elif op == "lt":
            if not self._numeric_compare(actual, expected, lambda a, b: a < b):
                return False, f"{condition.field} '{actual}' not < '{expected}'"
        elif op == "gte":
            if not self._numeric_compare(actual, expected, lambda a, b: a >= b):
                return False, f"{condition.field} '{actual}' not >= '{expected}'"
        elif op == "lte":
            if not self._numeric_compare(actual, expected, lambda a, b: a <= b):
                return False, f"{condition.field} '{actual}' not <= '{expected}'"
        elif op == "is_true":
            if actual.lower() not in ("true", "1", "yes"):
                return False, f"{condition.field} is not true"
        elif op == "is_false":
            if actual.lower() not in ("false", "0", "no", ""):
                return False, f"{condition.field} is not false"
        else:
            return False, f"Unknown operator: {op}"

        return True, ""

    @staticmethod
    def _numeric_compare(a: str, b: str, op) -> bool:
        try:
            return op(float(a), float(b))
        except (ValueError, TypeError):
            return False
