from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional

class BaseReporter(ABC):
    """
    Abstract Base Class for all report generators.
    Each reporter corresponds to an analysis stage and transforms its
    JSON output into a human-readable format like Markdown.
    """

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """The file extension for the report (e.g., 'md', 'html')."""
        pass

    @abstractmethod
    def generate_report(self, data: dict, df: Optional[pd.DataFrame] = None) -> str:
        """
        Generates a report from the stage's result data.

        Args:
            data (dict): The JSON output from the corresponding analysis stage.
            df (Optional[pd.DataFrame]): The original DataFrame, if needed for context.

        Returns:
            str: The content of the report as a string.
        """
        pass
