"""
Checkpoint management for walk-forward optimization resumability.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from src.backtest.optimization.walk_forward import CycleResult

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoint saving and loading for WFO cycles."""

    def __init__(self, checkpoint_dir: Path):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to save/load checkpoint files
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Checkpoint manager initialized: {self.checkpoint_dir}")

    def get_checkpoint_path(self, cycle_num: int) -> Path:
        """Get checkpoint file path for a cycle number."""
        return self.checkpoint_dir / f"cycle_{cycle_num:03d}.pkl"

    def save_cycle(self, cycle_result: CycleResult) -> None:
        """
        Save a completed cycle result to checkpoint.

        Args:
            cycle_result: Completed cycle result to save
        """
        checkpoint_path = self.get_checkpoint_path(cycle_result.cycle_num)
        logger.info(f"Saving checkpoint for cycle {cycle_result.cycle_num} to {checkpoint_path}")

        try:
            with open(checkpoint_path, "wb") as f:
                pickle.dump(cycle_result, f)
            logger.debug(f"Checkpoint saved successfully: {checkpoint_path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint for cycle {cycle_result.cycle_num}: {e}")
            raise

    def load_cycle(self, cycle_num: int) -> Optional[CycleResult]:
        """
        Load a cycle result from checkpoint.

        Args:
            cycle_num: Cycle number to load

        Returns:
            CycleResult if found, None otherwise
        """
        checkpoint_path = self.get_checkpoint_path(cycle_num)

        if not checkpoint_path.exists():
            logger.debug(f"No checkpoint found for cycle {cycle_num}")
            return None

        try:
            logger.debug(f"Loading checkpoint for cycle {cycle_num} from {checkpoint_path}")
            with open(checkpoint_path, "rb") as f:
                cycle_result = pickle.load(f)
            logger.debug(f"Checkpoint loaded successfully for cycle {cycle_num}")
            return cycle_result
        except Exception as e:
            logger.warning(f"Failed to load checkpoint for cycle {cycle_num}: {e}")
            return None

    def get_completed_cycles(self, total_cycles: int) -> dict[int, CycleResult]:
        """
        Get all completed cycles from checkpoints.

        Args:
            total_cycles: Total number of cycles expected

        Returns:
            Dictionary mapping cycle_num to CycleResult for completed cycles
        """
        completed = {}
        logger.info(f"Scanning for existing checkpoints in {self.checkpoint_dir}...")

        for cycle_num in range(1, total_cycles + 1):
            cycle_result = self.load_cycle(cycle_num)
            if cycle_result is not None:
                completed[cycle_num] = cycle_result

        if completed:
            logger.info(f"Found {len(completed)} completed cycles: {sorted(completed.keys())}")
        else:
            logger.info("No existing checkpoints found")

        return completed

    def clear_checkpoints(self) -> None:
        """Clear all checkpoint files."""
        logger.warning(f"Clearing all checkpoints in {self.checkpoint_dir}")
        for checkpoint_file in self.checkpoint_dir.glob("cycle_*.pkl"):
            checkpoint_file.unlink()
            logger.debug(f"Deleted {checkpoint_file}")

    def get_checkpoint_metadata(self) -> dict:
        """
        Get metadata about checkpoints without loading full data.

        Returns:
            Dictionary with checkpoint information
        """
        checkpoints = {}
        for checkpoint_file in sorted(self.checkpoint_dir.glob("cycle_*.pkl")):
            try:
                # Extract cycle number from filename
                cycle_num = int(checkpoint_file.stem.split("_")[1])
                checkpoints[cycle_num] = {
                    "path": str(checkpoint_file),
                    "size": checkpoint_file.stat().st_size,
                    "modified": datetime.fromtimestamp(checkpoint_file.stat().st_mtime),
                }
            except (ValueError, IndexError):
                continue

        return checkpoints
