"""
Task queue infrastructure for background job processing.

This module provides an SQLite-backed async task queue system with:
- Priority-based task scheduling
- Concurrent worker processing
- Automatic retry with exponential backoff
- Graceful shutdown handling
"""

from .task_manager import TaskManager
from .worker import BackgroundWorker

__all__ = [
    "TaskManager",
    "BackgroundWorker",
]
