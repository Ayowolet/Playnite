# Contributing to Playnite Python

Thank you for your interest in contributing to Playnite Python! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/playnite-python.git
   cd playnite-python
   ```
3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Development Workflow

1. Create a new branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following the code style guidelines below

3. Run tests to ensure everything works:
   ```bash
   pytest tests/
   ```

4. Format your code:
   ```bash
   black playnite_py/
   ```

5. Run linting:
   ```bash
   flake8 playnite_py/
   ```

6. Commit your changes with a descriptive commit message:
   ```bash
   git commit -m "Add feature: description of your changes"
   ```

7. Push to your fork and create a pull request

## Code Style

We follow PEP 8 with some modifications:

- **Line length**: 100 characters (not strict)
- **Imports**: Group imports as standard library, third-party, local
- **Naming conventions**:
  - `snake_case` for functions, methods, and variables
  - `PascalCase` for classes
  - `UPPER_CASE` for constants

### Example

```python
"""Module docstring."""

from typing import List, Optional

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session

from playnite_py.models import Game


class GameManager:
    """Manages game operations."""

    def __init__(self, session: Session):
        """Initialize manager."""
        self.session = session

    def get_games(self, limit: int = 50) -> List[Game]:
        """Get games with limit."""
        return self.session.query(Game).limit(limit).all()
```

## Testing

### Writing Tests

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Name test files as `test_<module_name>.py`
- Name test classes as `Test<FeatureName>`
- Name test functions as `test_<what_is_tested>`

### Example Test

```python
"""Unit tests for game operations."""

import pytest

from playnite_py.database import GameOperations


class TestGameOperations:
    """Test game CRUD operations."""

    def test_create_game(self, game_ops):
        """Test creating a game."""
        game = game_ops.create_game("Test Game")
        assert game.id is not None
        assert game.name == "Test Game"
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_database.py

# Run with coverage
pytest --cov=playnite_py

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

## Documentation

- Add docstrings to all public modules, classes, and functions
- Use Google-style docstrings:

```python
def filter_games(filter_config: dict, limit: int = 50) -> List[Game]:
    """
    Filter games based on configuration.

    Args:
        filter_config: Dictionary with filter criteria
        limit: Maximum number of results

    Returns:
        List of filtered games

    Raises:
        ValueError: If filter_config is invalid
    """
    pass
```

## Pull Request Guidelines

1. **Keep PRs focused**: One feature or bug fix per PR
2. **Write tests**: All new code should have tests
3. **Update documentation**: Update README or docstrings if needed
4. **Add entry to CHANGELOG**: Describe your changes
5. **Reference issues**: Link related issues in the PR description
6. **Keep commits clean**: Squash commits if needed

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe the tests you've added or run.

## Checklist
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] CHANGELOG updated

## Related Issues
Closes #123
```

## Feature Requests

For feature requests:

1. Check if the feature has already been requested
2. Create an issue with the "enhancement" label
3. Describe the feature and its use case
4. Be open to discussion about implementation

## Bug Reports

For bug reports:

1. Check if the bug has already been reported
2. Create an issue with the "bug" label
3. Include:
   - Description of the bug
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment (OS, Python version, etc.)
   - Relevant code or error messages

## Architecture Guidelines

### Headless Design

All core functionality must be testable without a GUI:

- Database operations are pure SQLAlchemy
- Controller system works in headless mode
- Navigation state machine is UI-agnostic
- CLI provides full functionality

### Separation of Concerns

- **Models**: Data structures only, no business logic
- **Database**: CRUD operations, queries
- **Organisation**: Filtering, searching, collections
- **Controller**: Input handling, no game logic
- **Navigation**: State machine, no rendering
- **CLI**: User interface, uses other modules

### Performance

- Keep queries efficient (use proper indexes)
- Test with 1000+ games
- Optimize for sub-second response times
- Profile slow operations

## Questions?

If you have questions about contributing, feel free to:

- Open an issue with the "question" label
- Join our Discord (link TBD)
- Email the maintainers

Thank you for contributing to Playnite Python!
