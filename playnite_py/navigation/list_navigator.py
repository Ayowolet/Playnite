"""List navigation utilities."""

from typing import Tuple, List


class ListNavigator:
    """Helper for navigating items in a list layout."""

    def __init__(self, total_items: int, page_size: int = 20):
        """
        Initialize list navigator.

        Args:
            total_items: Total number of items
            page_size: Number of items visible per page
        """
        self.total_items = total_items
        self.page_size = page_size

    def move_up(self, current_position: int, step: int = 1) -> int:
        """Move up by step items."""
        return max(0, current_position - step)

    def move_down(self, current_position: int, step: int = 1) -> int:
        """Move down by step items."""
        return min(self.total_items - 1, current_position + step)

    def page_up(self, current_position: int) -> int:
        """Move up one page."""
        return max(0, current_position - self.page_size)

    def page_down(self, current_position: int) -> int:
        """Move down one page."""
        return min(self.total_items - 1, current_position + self.page_size)

    def jump_to_top(self) -> int:
        """Jump to first item."""
        return 0

    def jump_to_bottom(self) -> int:
        """Jump to last item."""
        return max(0, self.total_items - 1)

    def get_current_page(self, current_position: int) -> int:
        """Get current page number (0-indexed)."""
        if self.page_size == 0:
            return 0
        return current_position // self.page_size

    def get_visible_range(self, current_position: int) -> Tuple[int, int]:
        """
        Get range of items visible on current page.

        Args:
            current_position: Current cursor position

        Returns:
            (start_position, end_position) tuple
        """
        page_number = self.get_current_page(current_position)
        start_position = page_number * self.page_size
        end_position = min(start_position + self.page_size, self.total_items)
        return (start_position, end_position)

    def get_page_items(self, current_position: int) -> List[int]:
        """
        Get list of item positions on current page.

        Args:
            current_position: Current cursor position

        Returns:
            List of item positions
        """
        start, end = self.get_visible_range(current_position)
        return list(range(start, end))

    def get_total_pages(self) -> int:
        """Get total number of pages."""
        if self.page_size == 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size
