"""Factory for creating filter rules and pipeline from config."""

from typing import Any, Mapping
from pathlib import Path
import yaml

from .base import BaseFilterRule
from .pipeline import FilterPipeline
from .rules.supertrend import SupertrendFilter


def _create_rule(rule_name: str, rule_config: Mapping[str, Any]) -> BaseFilterRule | None:
    """Create a filter rule instance from config.
    
    Args:
        rule_name: Name of the rule (e.g., "supertrend")
        rule_config: Rule configuration dict with "enabled" and "params"
        
    Returns:
        Rule instance if enabled, None otherwise
    """
    if not rule_config.get("enabled", False):
        return None

    params = rule_config.get("params", {})

    # Map rule names to classes
    rule_classes: dict[str, type[BaseFilterRule]] = {
        "supertrend": SupertrendFilter,
        "low_volatility_pct": None,  # Old filter - not compatible with new system
    }

    rule_class = rule_classes.get(rule_name)
    if rule_class is None:
        print(f"Warning: Unknown filter rule '{rule_name}', skipping")
        return None

    try:
        return rule_class(params)
    except Exception as e:
        print(f"Warning: Failed to create filter rule '{rule_name}': {e}")
        return None


def load_filter_pipeline(config_path: str | Path) -> FilterPipeline | None:
    """Load filter pipeline from YAML config file.
    
    Args:
        config_path: Path to filters.yaml config file
        
    Returns:
        FilterPipeline instance, or None if no rules enabled
    """
    config_path = Path(config_path)
    if not config_path.exists():
        return None

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    logic_mode = config.get("logic_mode", "AND")
    rules_config = config.get("rules", {})

    # Create enabled rules
    rules: list[BaseFilterRule] = []
    for rule_name, rule_config in rules_config.items():
        rule = _create_rule(rule_name, rule_config)
        if rule is not None:
            rules.append(rule)

    if not rules:
        return None

    return FilterPipeline(rules=rules, logic_mode=logic_mode)
