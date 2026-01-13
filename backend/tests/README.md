# Good Signal Backend Tests

Comprehensive test suite for the good-signal backend Phase 1 (Backend Foundation).

## Test Structure

```
backend/tests/
├── __init__.py
├── conftest.py              # Pytest fixtures and configuration
├── unit/                    # Unit tests (isolated component tests)
│   ├── __init__.py
│   ├── test_task_manager.py  # TaskManager unit tests
│   └── test_risk_service.py  # RiskStateRepository unit tests
└── integration/             # Integration tests (API and database)
    ├── __init__.py
    ├── test_health_api.py    # Health endpoint integration tests
    └── test_database.py      # Database initialization tests
```

## Installation

Install test dependencies:

```bash
# From project root
pip install -r backend/requirements-test.txt
```

## Running Tests

### Run All Tests

```bash
# From project root
pytest backend/tests/

# Or with coverage report
pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest backend/tests/unit/

# Integration tests only
pytest backend/tests/integration/

# Run tests by marker
pytest -m unit
pytest -m integration
```

### Run Specific Test Files

```bash
# Test TaskManager
pytest backend/tests/unit/test_task_manager.py

# Test Risk Service
pytest backend/tests/unit/test_risk_service.py

# Test Health API
pytest backend/tests/integration/test_health_api.py

# Test Database
pytest backend/tests/integration/test_database.py
```

### Run Specific Test Classes or Functions

```bash
# Run specific test class
pytest backend/tests/unit/test_task_manager.py::TestTaskManagerEnqueue

# Run specific test function
pytest backend/tests/unit/test_task_manager.py::TestTaskManagerEnqueue::test_enqueue_task_returns_id
```

### Parallel Execution

Run tests in parallel for faster execution:

```bash
# Use 4 parallel workers
pytest backend/tests/ -n 4

# Use auto-detect CPU count
pytest backend/tests/ -n auto
```

### Verbose Output

```bash
# Show detailed test output
pytest backend/tests/ -v

# Show print statements
pytest backend/tests/ -s

# Show detailed failure info
pytest backend/tests/ -vv
```

## Test Coverage

Generate coverage reports:

```bash
# Terminal report with missing lines
pytest backend/tests/ --cov=backend --cov-report=term-missing

# HTML coverage report (opens in browser)
pytest backend/tests/ --cov=backend --cov-report=html
open htmlcov/index.html

# XML coverage report (for CI/CD)
pytest backend/tests/ --cov=backend --cov-report=xml
```

## Test Categories

### Unit Tests

Test individual components in isolation with mocked dependencies.

**test_task_manager.py** - TaskManager tests:
- Task enqueuing with priority and scheduling
- Task claiming with atomic operations
- Task completion and failure handling
- Retry logic and max attempts
- Task cancellation
- Task status retrieval
- Helper methods (pending count, running tasks)

**test_risk_service.py** - RiskStateRepository tests:
- Risk state initialization and singleton pattern
- Kill switch activation/deactivation
- Daily P&L tracking (wins, losses, mixed)
- Daily counter reset (automatic and manual)
- Exposure tracking
- Risk limit checking with automatic kill switch
- Helper methods (daily stats, trade count)

### Integration Tests

Test multiple components working together, including APIs and database.

**test_health_api.py** - Health endpoint tests:
- Basic health check (liveness)
- Readiness check with dependency status
- Liveness probe endpoint
- Response structure validation
- Performance tests

**test_database.py** - Database tests:
- Database initialization
- All 7 tables created correctly
- Table structure validation (columns, types)
- Foreign key relationships
- Primary keys and constraints
- Indexes for performance
- Session operations (commit, rollback)

## Fixtures

Key fixtures available in `conftest.py`:

- `test_db_path` - Temporary SQLite database path
- `test_settings` - Test configuration with test database
- `async_engine` - Async database engine for tests
- `session_factory` - Session factory for creating test sessions
- `async_session` - Async database session with auto-commit/rollback
- `clean_db` - Clean database session (reset after each test)
- `test_client` - AsyncClient for API testing
- `sample_task_payload` - Sample task data for tests
- `sample_backtest_config` - Sample backtest configuration
- `sample_live_config` - Sample live trading configuration

## Writing New Tests

### Unit Test Template

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

@pytest.mark.asyncio
class TestMyComponent:
    """Test MyComponent functionality."""

    async def test_my_feature(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that my feature works correctly."""
        # Arrange
        component = MyComponent(session_factory=session_factory)

        # Act
        result = await component.my_method()

        # Assert
        assert result is not None
```

### Integration Test Template

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
class TestMyAPI:
    """Test MyAPI endpoints."""

    async def test_my_endpoint(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that my endpoint returns expected data."""
        # Act
        response = await test_client.get("/api/my-endpoint")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "field" in data
```

## Best Practices

1. **Isolation** - Each test should be independent and not rely on other tests
2. **Arrange-Act-Assert** - Follow AAA pattern for clarity
3. **Descriptive Names** - Test names should describe what they test
4. **One Assertion Per Test** - Focus on testing one thing at a time
5. **Use Fixtures** - Leverage fixtures for setup and teardown
6. **Async/Await** - Use `pytest.mark.asyncio` for async tests
7. **Clean Database** - Use `clean_db` fixture for database isolation
8. **Edge Cases** - Test both happy path and error cases

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements-test.txt
      - name: Run tests
        run: |
          pytest backend/tests/ --cov=backend --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Import Errors

If you encounter import errors, ensure you're running tests from the project root:

```bash
cd E:\Personal\GitHub\good-signal
pytest backend/tests/
```

### Database Lock Errors

If you encounter SQLite lock errors, ensure:
1. Tests are using `clean_db` fixture for isolation
2. Sessions are properly closed after tests
3. No lingering database connections

### Async Test Failures

Ensure:
1. Test functions are marked with `@pytest.mark.asyncio`
2. All async functions use `await`
3. Fixtures are using `pytest_asyncio.fixture` for async fixtures

## Test Metrics

Current test coverage targets:
- Minimum coverage: 80%
- Goal coverage: 90%+
- Critical paths: 100% coverage

Test count by category:
- Unit tests: 50+ tests
- Integration tests: 30+ tests
- Total: 80+ comprehensive tests
