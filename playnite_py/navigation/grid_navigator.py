"""Grid navigation utilities."""

from typing import Tuple, List


class GridNavigator:
    """Helper for navigating items in a grid layout."""

    def __init__(self, columns: int, rows: int, total_items: int):
        """
        Initialize grid navigator.

        Args:
            columns: Number of columns in grid
            rows: Number of rows visible per page
            total_items: Total number of items
        """
        self.columns = columns
        self.rows = rows
        self.total_items = total_items

    def position_to_coords(self, position: int) -> Tuple[int, int]:
        """
        Convert linear position to grid coordinates.

        Args:
            position: Linear position (0-indexed)

        Returns:
            (row, column) tuple
        """
        if self.columns == 0:
            return (0, 0)
        row = position // self.columns
        col = position % self.columns
        return (row, col)

    def coords_to_position(self, row: int, col: int) -> int:
        """
        Convert grid coordinates to linear position.

        Args:
            row: Row number
            col: Column number

        Returns:
            Linear position
        """
        position = row * self.columns + col
        return min(position, self.total_items - 1)

    def move_up(self, current_position: int) -> int:
        """Move up one row."""
        row, col = self.position_to_coords(current_position)
        new_row = max(0, row - 1)
        return self.coords_to_position(new_row, col)

    def move_down(self, current_position: int) -> int:
        """Move down one row."""
        row, col = self.position_to_coords(current_position)
        max_row = (self.total_items - 1) // self.columns
        new_row = min(max_row, row + 1)
        return self.coords_to_position(new_row, col)

    def move_left(self, current_position: int) -> int:
        """Move left one column."""
        row, col = self.position_to_coords(current_position)
        new_col = max(0, col - 1)
        return self.coords_to_position(row, new_col)

    def move_right(self, current_position: int) -> int:
        """Move right one column."""
        row, col = self.position_to_coords(current_position)
        new_col = min(self.columns - 1, col + 1)
        new_pos = self.coords_to_position(row, new_col)
        return min(new_pos, self.total_items - 1)

    def page_up(self, current_position: int) -> int:
        """Move up one page."""
        row, col = self.position_to_coords(current_position)
        new_row = max(0, row - self.rows)
        return self.coords_to_position(new_row, col)

    def page_down(self, current_position: int) -> int:
        """Move down one page."""
        row, col = self.position_to_coords(current_position)
        max_row = (self.total_items - 1) // self.columns
        new_row = min(max_row, row + self.rows)
        return self.coords_to_position(new_row, col)

    def get_visible_range(self, current_position: int) -> Tuple[int, int]:
        """
        Get range of items visible on current page.

        Args:
            current_position: Current cursor position

        Returns:
            (start_position, end_position) tuple
        """
        row, _ = self.position_to_coords(current_position)
        page_number = row // self.rows
        start_position = page_number * self.rows * self.columns
        end_position = min(start_position + self.rows * self.columns, self.total_items)
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
