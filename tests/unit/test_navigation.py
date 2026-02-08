"""Unit tests for navigation system."""

import pytest

from playnite_py.navigation import (
    NavigationStateMachine, UIState, NavigationCommand,
    GridNavigator, ListNavigator
)


class TestNavigationStateMachine:
    """Test navigation state machine."""

    def test_init(self):
        """Test initialization."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        assert nav.get_current_state() == UIState.GAME_GRID

    def test_state_transitions(self):
        """Test state transitions."""
        nav = NavigationStateMachine(UIState.MAIN_MENU)

        # Main menu -> Game grid
        nav.handle_command(NavigationCommand.SELECT)
        assert nav.get_current_state() == UIState.GAME_GRID

        # Game grid -> Game details
        nav.handle_command(NavigationCommand.SELECT)
        assert nav.get_current_state() == UIState.GAME_DETAILS

        # Game details -> Back to grid
        nav.handle_command(NavigationCommand.BACK)
        assert nav.get_current_state() == UIState.GAME_GRID

    def test_cursor_movement_grid(self):
        """Test cursor movement in grid view."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        nav.set_grid_layout(4, 3)  # 4 columns, 3 rows
        nav.set_total_items(20)
        nav.set_cursor_position(0)

        # Move right
        nav.handle_command(NavigationCommand.RIGHT)
        assert nav.get_cursor_position() == 1

        # Move down
        nav.handle_command(NavigationCommand.DOWN)
        assert nav.get_cursor_position() == 5  # 1 + 4 columns

        # Move left
        nav.handle_command(NavigationCommand.LEFT)
        assert nav.get_cursor_position() == 4

        # Move up
        nav.handle_command(NavigationCommand.UP)
        assert nav.get_cursor_position() == 0

    def test_cursor_movement_list(self):
        """Test cursor movement in list view."""
        nav = NavigationStateMachine(UIState.GAME_LIST)
        nav.set_view_mode('list')
        nav.set_total_items(50)
        nav.context.page_size = 20
        nav.set_cursor_position(0)

        # Move down
        nav.handle_command(NavigationCommand.DOWN)
        assert nav.get_cursor_position() == 1

        # Move up
        nav.handle_command(NavigationCommand.UP)
        assert nav.get_cursor_position() == 0

        # Page down
        nav.handle_command(NavigationCommand.PAGE_DOWN)
        assert nav.get_cursor_position() == 20

        # Page up
        nav.handle_command(NavigationCommand.PAGE_UP)
        assert nav.get_cursor_position() == 0

    def test_cursor_boundaries(self):
        """Test cursor stays within boundaries."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        nav.set_total_items(10)
        nav.set_cursor_position(0)

        # Try to move up from position 0
        nav.handle_command(NavigationCommand.UP)
        assert nav.get_cursor_position() == 0

        # Move to last item
        nav.set_cursor_position(9)

        # Try to move down past last item
        nav.handle_command(NavigationCommand.DOWN)
        assert nav.get_cursor_position() == 9

    def test_state_history(self):
        """Test state history tracking."""
        nav = NavigationStateMachine(UIState.MAIN_MENU)
        nav.handle_command(NavigationCommand.SELECT)  # -> GAME_GRID
        nav.handle_command(NavigationCommand.FILTER)  # -> FILTER_MENU

        context = nav.get_context()
        assert len(context.state_history) == 2
        assert UIState.MAIN_MENU in context.state_history

    def test_go_back(self):
        """Test going back through history."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        nav.handle_command(NavigationCommand.SELECT)  # -> GAME_DETAILS
        nav.handle_command(NavigationCommand.BACK)    # -> GAME_GRID

        assert nav.get_current_state() == UIState.GAME_GRID

    def test_state_listeners(self):
        """Test state change listeners."""
        nav = NavigationStateMachine(UIState.MAIN_MENU)
        states_changed = []

        def listener(old_state, new_state, context):
            states_changed.append((old_state, new_state))

        nav.register_state_change_listener(listener)
        nav.handle_command(NavigationCommand.SELECT)

        assert len(states_changed) == 1
        assert states_changed[0][0] == UIState.MAIN_MENU
        assert states_changed[0][1] == UIState.GAME_GRID

    def test_cursor_listeners(self):
        """Test cursor move listeners."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        nav.set_total_items(10)
        cursor_positions = []

        def listener(context):
            cursor_positions.append(context.cursor_position)

        nav.register_cursor_move_listener(listener)
        nav.handle_command(NavigationCommand.DOWN)

        assert len(cursor_positions) > 0

    def test_context_to_dict(self):
        """Test converting context to dictionary."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        nav.set_total_items(50)
        nav.set_cursor_position(10)

        context_dict = nav.get_context().to_dict()

        assert context_dict['current_state'] == 'game_grid'
        assert context_dict['cursor_position'] == 10
        assert context_dict['total_items'] == 50

    def test_reset(self):
        """Test resetting state machine."""
        nav = NavigationStateMachine(UIState.GAME_GRID)
        nav.set_cursor_position(10)
        nav.handle_command(NavigationCommand.SELECT)

        nav.reset()

        assert nav.get_current_state() == UIState.GAME_GRID
        assert nav.get_cursor_position() == 0


class TestGridNavigator:
    """Test grid navigator utility."""

    def test_position_to_coords(self):
        """Test converting position to coordinates."""
        nav = GridNavigator(columns=4, rows=3, total_items=20)

        row, col = nav.position_to_coords(0)
        assert (row, col) == (0, 0)

        row, col = nav.position_to_coords(5)
        assert (row, col) == (1, 1)

        row, col = nav.position_to_coords(9)
        assert (row, col) == (2, 1)

    def test_coords_to_position(self):
        """Test converting coordinates to position."""
        nav = GridNavigator(columns=4, rows=3, total_items=20)

        pos = nav.coords_to_position(0, 0)
        assert pos == 0

        pos = nav.coords_to_position(1, 2)
        assert pos == 6

    def test_move_up(self):
        """Test moving up."""
        nav = GridNavigator(columns=4, rows=3, total_items=20)

        new_pos = nav.move_up(5)
        assert new_pos == 1

        # At top, should stay
        new_pos = nav.move_up(0)
        assert new_pos == 0

    def test_move_down(self):
        """Test moving down."""
        nav = GridNavigator(columns=4, rows=3, total_items=20)

        new_pos = nav.move_down(0)
        assert new_pos == 4

        new_pos = nav.move_down(1)
        assert new_pos == 5

    def test_move_left(self):
        """Test moving left."""
        nav = GridNavigator(columns=4, rows=3, total_items=20)

        new_pos = nav.move_left(5)
        assert new_pos == 4

        # At left edge
        new_pos = nav.move_left(0)
        assert new_pos == 0

    def test_move_right(self):
        """Test moving right."""
        nav = GridNavigator(columns=4, rows=3, total_items=20)

        new_pos = nav.move_right(0)
        assert new_pos == 1

        new_pos = nav.move_right(5)
        assert new_pos == 6

    def test_page_down(self):
        """Test paging down."""
        nav = GridNavigator(columns=4, rows=3, total_items=50)

        new_pos = nav.page_down(0)
        assert new_pos == 12  # 3 rows * 4 columns

    def test_page_up(self):
        """Test paging up."""
        nav = GridNavigator(columns=4, rows=3, total_items=50)

        new_pos = nav.page_up(12)
        assert new_pos == 0

    def test_get_visible_range(self):
        """Test getting visible range."""
        nav = GridNavigator(columns=4, rows=3, total_items=50)

        start, end = nav.get_visible_range(0)
        assert start == 0
        assert end == 12

        start, end = nav.get_visible_range(15)
        assert start == 12
        assert end == 24


class TestListNavigator:
    """Test list navigator utility."""

    def test_move_up(self):
        """Test moving up."""
        nav = ListNavigator(total_items=50, page_size=20)

        new_pos = nav.move_up(5)
        assert new_pos == 4

        # At top
        new_pos = nav.move_up(0)
        assert new_pos == 0

    def test_move_down(self):
        """Test moving down."""
        nav = ListNavigator(total_items=50, page_size=20)

        new_pos = nav.move_down(5)
        assert new_pos == 6

        # At bottom
        new_pos = nav.move_down(49)
        assert new_pos == 49

    def test_page_down(self):
        """Test paging down."""
        nav = ListNavigator(total_items=50, page_size=20)

        new_pos = nav.page_down(0)
        assert new_pos == 20

        new_pos = nav.page_down(20)
        assert new_pos == 40

    def test_page_up(self):
        """Test paging up."""
        nav = ListNavigator(total_items=50, page_size=20)

        new_pos = nav.page_up(40)
        assert new_pos == 20

        new_pos = nav.page_up(20)
        assert new_pos == 0

    def test_jump_to_top(self):
        """Test jumping to top."""
        nav = ListNavigator(total_items=50)

        pos = nav.jump_to_top()
        assert pos == 0

    def test_jump_to_bottom(self):
        """Test jumping to bottom."""
        nav = ListNavigator(total_items=50)

        pos = nav.jump_to_bottom()
        assert pos == 49

    def test_get_current_page(self):
        """Test getting current page."""
        nav = ListNavigator(total_items=50, page_size=20)

        page = nav.get_current_page(0)
        assert page == 0

        page = nav.get_current_page(25)
        assert page == 1

    def test_get_visible_range(self):
        """Test getting visible range."""
        nav = ListNavigator(total_items=50, page_size=20)

        start, end = nav.get_visible_range(0)
        assert start == 0
        assert end == 20

        start, end = nav.get_visible_range(25)
        assert start == 20
        assert end == 40

    def test_get_total_pages(self):
        """Test getting total pages."""
        nav = ListNavigator(total_items=50, page_size=20)
        assert nav.get_total_pages() == 3

        nav = ListNavigator(total_items=60, page_size=20)
        assert nav.get_total_pages() == 3
