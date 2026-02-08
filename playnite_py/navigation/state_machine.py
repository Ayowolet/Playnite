"""Navigation state machine for UI navigation."""

from typing import Optional, Dict, Any, Callable, List
from enum import Enum
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class UIState(Enum):
    """UI states for navigation."""
    MAIN_MENU = "main_menu"
    GAME_GRID = "game_grid"
    GAME_LIST = "game_list"
    GAME_DETAILS = "game_details"
    FILTER_MENU = "filter_menu"
    SEARCH = "search"
    SETTINGS = "settings"
    COLLECTION_VIEW = "collection_view"


class NavigationCommand(Enum):
    """Navigation commands."""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SELECT = "select"
    BACK = "back"
    MENU = "menu"
    FAVORITE = "favorite"
    FILTER = "filter"
    SEARCH = "search"
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"


@dataclass
class NavigationContext:
    """Context for current navigation state."""
    current_state: UIState
    cursor_position: int = 0
    selected_item_id: Optional[int] = None
    total_items: int = 0
    page_size: int = 20
    current_page: int = 0
    view_mode: str = "grid"  # grid, list, details
    grid_columns: int = 4
    grid_rows: int = 3
    state_data: Dict[str, Any] = field(default_factory=dict)
    state_history: List[UIState] = field(default_factory=list)

    def get_grid_position(self) -> tuple:
        """Get current grid position as (row, col)."""
        if self.grid_columns == 0:
            return (0, 0)
        row = self.cursor_position // self.grid_columns
        col = self.cursor_position % self.grid_columns
        return (row, col)

    def set_grid_position(self, row: int, col: int):
        """Set cursor position from grid coordinates."""
        self.cursor_position = row * self.grid_columns + col

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return {
            'current_state': self.current_state.value,
            'cursor_position': self.cursor_position,
            'selected_item_id': self.selected_item_id,
            'total_items': self.total_items,
            'page_size': self.page_size,
            'current_page': self.current_page,
            'view_mode': self.view_mode,
            'grid_columns': self.grid_columns,
            'grid_rows': self.grid_rows,
            'state_data': self.state_data,
            'state_history': [s.value for s in self.state_history]
        }


class NavigationStateMachine:
    """
    State machine for UI navigation.

    Handles state transitions and cursor movement without any rendering logic.
    Fully testable in headless mode.
    """

    def __init__(self, initial_state: UIState = UIState.GAME_GRID):
        """
        Initialize navigation state machine.

        Args:
            initial_state: Starting UI state
        """
        self.context = NavigationContext(current_state=initial_state)
        self.transition_handlers: Dict[UIState, Dict[NavigationCommand, Callable]] = {}
        self.state_change_listeners: List[Callable] = []
        self.cursor_move_listeners: List[Callable] = []

        self._setup_default_transitions()

    def _setup_default_transitions(self):
        """Set up default state transitions."""
        # Main menu transitions
        self.register_transition(
            UIState.MAIN_MENU,
            NavigationCommand.SELECT,
            self._transition_to_game_grid
        )

        # Game grid transitions
        self.register_transition(
            UIState.GAME_GRID,
            NavigationCommand.BACK,
            self._transition_to_main_menu
        )
        self.register_transition(
            UIState.GAME_GRID,
            NavigationCommand.SELECT,
            self._transition_to_game_details
        )
        self.register_transition(
            UIState.GAME_GRID,
            NavigationCommand.FILTER,
            self._transition_to_filter_menu
        )
        self.register_transition(
            UIState.GAME_GRID,
            NavigationCommand.SEARCH,
            self._transition_to_search
        )

        # Game details transitions
        self.register_transition(
            UIState.GAME_DETAILS,
            NavigationCommand.BACK,
            self._transition_to_game_grid
        )

        # Filter menu transitions
        self.register_transition(
            UIState.FILTER_MENU,
            NavigationCommand.BACK,
            self._go_back
        )

        # Search transitions
        self.register_transition(
            UIState.SEARCH,
            NavigationCommand.BACK,
            self._go_back
        )

    def register_transition(self, state: UIState, command: NavigationCommand,
                            handler: Callable):
        """
        Register a transition handler for a state and command.

        Args:
            state: Current state
            command: Navigation command
            handler: Handler function
        """
        if state not in self.transition_handlers:
            self.transition_handlers[state] = {}
        self.transition_handlers[state][command] = handler

    def register_state_change_listener(self, callback: Callable):
        """Register callback for state changes."""
        self.state_change_listeners.append(callback)

    def register_cursor_move_listener(self, callback: Callable):
        """Register callback for cursor movements."""
        self.cursor_move_listeners.append(callback)

    def handle_command(self, command: NavigationCommand) -> bool:
        """
        Handle a navigation command.

        Args:
            command: Navigation command to handle

        Returns:
            True if command was handled
        """
        # Handle cursor movement commands
        if command in [NavigationCommand.UP, NavigationCommand.DOWN,
                       NavigationCommand.LEFT, NavigationCommand.RIGHT,
                       NavigationCommand.PAGE_UP, NavigationCommand.PAGE_DOWN]:
            return self._handle_cursor_movement(command)

        # Handle state transitions
        current_state = self.context.current_state
        if current_state in self.transition_handlers:
            if command in self.transition_handlers[current_state]:
                handler = self.transition_handlers[current_state][command]
                handler()
                return True

        return False

    def _handle_cursor_movement(self, command: NavigationCommand) -> bool:
        """Handle cursor movement commands."""
        old_position = self.context.cursor_position

        if self.context.view_mode == "grid":
            self._handle_grid_movement(command)
        else:
            self._handle_list_movement(command)

        if old_position != self.context.cursor_position:
            self._notify_cursor_move()
            return True

        return False

    def _handle_grid_movement(self, command: NavigationCommand):
        """Handle cursor movement in grid view."""
        row, col = self.context.get_grid_position()

        if command == NavigationCommand.UP:
            row = max(0, row - 1)
        elif command == NavigationCommand.DOWN:
            row = min((self.context.total_items - 1) // self.context.grid_columns, row + 1)
        elif command == NavigationCommand.LEFT:
            col = max(0, col - 1)
        elif command == NavigationCommand.RIGHT:
            col = min(self.context.grid_columns - 1, col + 1)
        elif command == NavigationCommand.PAGE_DOWN:
            row = min((self.context.total_items - 1) // self.context.grid_columns,
                      row + self.context.grid_rows)
        elif command == NavigationCommand.PAGE_UP:
            row = max(0, row - self.context.grid_rows)

        self.context.set_grid_position(row, col)
        self.context.cursor_position = min(self.context.cursor_position,
                                            self.context.total_items - 1)

    def _handle_list_movement(self, command: NavigationCommand):
        """Handle cursor movement in list view."""
        if command == NavigationCommand.UP:
            self.context.cursor_position = max(0, self.context.cursor_position - 1)
        elif command == NavigationCommand.DOWN:
            self.context.cursor_position = min(self.context.total_items - 1,
                                                self.context.cursor_position + 1)
        elif command == NavigationCommand.PAGE_DOWN:
            self.context.cursor_position = min(self.context.total_items - 1,
                                                self.context.cursor_position + self.context.page_size)
        elif command == NavigationCommand.PAGE_UP:
            self.context.cursor_position = max(0, self.context.cursor_position - self.context.page_size)

    def _transition_to_state(self, new_state: UIState):
        """Transition to a new state."""
        old_state = self.context.current_state
        self.context.state_history.append(old_state)
        self.context.current_state = new_state
        self._notify_state_change(old_state, new_state)

    def _transition_to_main_menu(self):
        """Transition to main menu."""
        self._transition_to_state(UIState.MAIN_MENU)

    def _transition_to_game_grid(self):
        """Transition to game grid."""
        self._transition_to_state(UIState.GAME_GRID)

    def _transition_to_game_details(self):
        """Transition to game details."""
        self._transition_to_state(UIState.GAME_DETAILS)

    def _transition_to_filter_menu(self):
        """Transition to filter menu."""
        self._transition_to_state(UIState.FILTER_MENU)

    def _transition_to_search(self):
        """Transition to search."""
        self._transition_to_state(UIState.SEARCH)

    def _go_back(self):
        """Go back to previous state."""
        if self.context.state_history:
            previous_state = self.context.state_history.pop()
            old_state = self.context.current_state
            self.context.current_state = previous_state
            self._notify_state_change(old_state, previous_state)

    def _notify_state_change(self, old_state: UIState, new_state: UIState):
        """Notify listeners of state change."""
        for listener in self.state_change_listeners:
            try:
                listener(old_state, new_state, self.context)
            except Exception as e:
                logger.error(f"Error in state change listener: {e}", exc_info=True)

    def _notify_cursor_move(self):
        """Notify listeners of cursor movement."""
        for listener in self.cursor_move_listeners:
            try:
                listener(self.context)
            except Exception as e:
                logger.error(f"Error in cursor move listener: {e}", exc_info=True)

    def get_current_state(self) -> UIState:
        """Get current UI state."""
        return self.context.current_state

    def get_cursor_position(self) -> int:
        """Get current cursor position."""
        return self.context.cursor_position

    def set_cursor_position(self, position: int):
        """Set cursor position."""
        old_position = self.context.cursor_position
        self.context.cursor_position = max(0, min(position, self.context.total_items - 1))
        if old_position != self.context.cursor_position:
            self._notify_cursor_move()

    def set_total_items(self, count: int):
        """Set total number of items in current view."""
        self.context.total_items = count
        if self.context.cursor_position >= count:
            self.set_cursor_position(max(0, count - 1))

    def set_view_mode(self, mode: str):
        """Set view mode (grid, list, details)."""
        self.context.view_mode = mode

    def set_grid_layout(self, columns: int, rows: int):
        """Set grid layout dimensions."""
        self.context.grid_columns = columns
        self.context.grid_rows = rows

    def get_context(self) -> NavigationContext:
        """Get current navigation context."""
        return self.context

    def reset(self):
        """Reset state machine to initial state."""
        self.context = NavigationContext(current_state=UIState.GAME_GRID)
