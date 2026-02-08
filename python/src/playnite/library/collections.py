"""Smart collection rule evaluation."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from ..database.models import Game, SmartCollection

logger = logging.getLogger(__name__)


# Operator implementations keyed by name
_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "equals": lambda a, b: str(a).lower() == str(b).lower() if isinstance(b, str) else a == b,
    "not_equals": lambda a, b: not (str(a).lower() == str(b).lower() if isinstance(b, str) else a == b),
    "contains": lambda a, b: str(b).lower() in str(a).lower() if a is not None else False,
    "not_contains": lambda a, b: str(b).lower() not in str(a).lower() if a is not None else True,
    "gt": lambda a, b: a > b if a is not None else False,
    "lt": lambda a, b: a < b if a is not None else False,
    "gte": lambda a, b: a >= b if a is not None else False,
    "lte": lambda a, b: a <= b if a is not None else False,
    "in": lambda a, b: a in b if isinstance(b, list) else False,
    "not_in": lambda a, b: a not in b if isinstance(b, list) else True,
    "is_true": lambda a, _b: bool(a),
    "is_false": lambda a, _b: not bool(a),
}

# Fields that return lists of names rather than scalars
_LIST_FIELDS = {
    "tag_names": lambda g: [t.name for t in g.tags],
    "genre_names": lambda g: [genre.name for genre in g.genres],
    "category_names": lambda g: [c.name for c in g.categories],
    "platform_names": lambda g: [p.name for p in g.platforms],
}

# Allowlist of fields that rules may reference — prevents attribute traversal attacks
_ALLOWED_RULE_FIELDS = frozenset(_LIST_FIELDS) | frozenset({
    "name", "release_year", "playtime", "completion_status",
    "developer", "publisher", "user_score",
    "is_favorite", "is_hidden", "is_installed",
})


def validate_rules(rules: list) -> None:
    """Raise ValueError if any rule dict is malformed."""
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule {i} must be a dict")
        field = rule.get("field", "")
        operator = rule.get("operator", "")
        if field not in _ALLOWED_RULE_FIELDS:
            raise ValueError(f"Rule {i}: unknown field {field!r}")
        if operator not in _OPS:
            raise ValueError(f"Rule {i}: unknown operator {operator!r}")
        if "value" not in rule and operator not in ("is_true", "is_false"):
            raise ValueError(f"Rule {i}: missing 'value'")


class CollectionEvaluator:
    """Evaluates smart-collection rules against Game instances."""

    def _field_value(self, game: Game, field: str) -> Any:
        if field not in _ALLOWED_RULE_FIELDS:
            return None
        if field in _LIST_FIELDS:
            return _LIST_FIELDS[field](game)
        return getattr(game, field, None)

    def evaluate_rule(self, game: Game, rule: dict) -> bool:
        """Return True if *game* satisfies a single rule dict."""
        field = rule.get("field", "")
        operator = rule.get("operator", "equals")
        value = rule.get("value")

        op = _OPS.get(operator)
        if op is None:
            logger.warning("Unknown rule operator %r for field %r; rule skipped", operator, field)
            return False

        game_value = self._field_value(game, field)

        # For list-type fields apply the operator to each element
        if isinstance(game_value, list):
            if operator in ("contains", "equals", "in"):
                return any(op(item, value) for item in game_value)
            if operator in ("not_contains", "not_equals", "not_in"):
                return all(op(item, value) for item in game_value)

        try:
            return op(game_value, value)
        except (TypeError, ValueError):
            return False

    def evaluate_collection(self, game: Game, collection: SmartCollection) -> bool:
        """Return True if *game* matches all (AND) or any (OR) rules."""
        rules = collection.rules or []
        if not rules:
            return True
        results = [self.evaluate_rule(game, r) for r in rules]
        return any(results) if collection.logic == "OR" else all(results)

    def get_matching_games(self, games: List[Game], collection: SmartCollection) -> List[Game]:
        """Filter *games* to those matching the collection rules."""
        return [g for g in games if self.evaluate_collection(g, collection)]
