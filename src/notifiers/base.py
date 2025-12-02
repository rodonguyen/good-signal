"""
Abstract base class for all notification systems.
Ensures consistent notification interface.
"""
from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """
    Base class for all notification implementations.
    
    All notifiers must implement send() which:
    - Accepts a message string
    - Sends via appropriate channel (Discord, Telegram, etc.)
    - Returns success/failure boolean
    """
    
    @abstractmethod
    def send(self, message: str) -> bool:
        """
        Send notification message.
        
        Args:
            message: Formatted message string to send
            
        Returns:
            True if sent successfully, False otherwise
            
        Implementation should:
        - Handle connection errors gracefully
        - Log failures
        - Not raise exceptions (return False instead)
        """
        pass
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}()"

