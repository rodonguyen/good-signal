"""Configuration utilities for loading settings."""
import yaml
from pathlib import Path
from typing import Dict, Any


def load_config(config_path: str = "src/config/crypto_symbols.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Dictionary containing configuration
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def get_symbol_config(symbol: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get configuration for a specific symbol.
    
    Args:
        symbol: Symbol name (e.g., 'ETHUSDT')
        config: Optional pre-loaded config dict
        
    Returns:
        Symbol configuration dictionary
    """
    if config is None:
        config = load_config()
    
    if symbol not in config['symbols']:
        raise ValueError(f"Symbol '{symbol}' not found in configuration. "
                        f"Available symbols: {list(config['symbols'].keys())}")
    
    return config['symbols'][symbol]


def get_default_symbol(config: Dict[str, Any] = None) -> str:
    """Get default symbol from configuration.
    
    Args:
        config: Optional pre-loaded config dict
        
    Returns:
        Default symbol name
    """
    if config is None:
        config = load_config()
    
    return config.get('default_symbol', 'ETHUSDT')



