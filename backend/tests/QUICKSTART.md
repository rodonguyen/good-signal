# Test Suite Quick Start Guide

Quick reference for running the good-signal backend test suite.

## Installation

```bash
# Install test dependencies
cd E:\Personal\GitHub\good-signal
pip install -r backend/requirements-test.txt
```

## Run All Tests

```bash
# From project root
pytest backend/tests/

# With coverage
pytest backend/tests/ --cov=backend --cov-report=term-missing
```

## Quick Commands

```bash
# Unit tests only
pytest backend/tests/unit/

# Integration tests only
pytest backend/tests/integration/

# Run in parallel (faster)
pytest backend/tests/ -n auto

# Verbose output
pytest backend/tests/ -v

# Stop on first failure
pytest backend/tests/ -x

# Show print statements
pytest backend/tests/ -s
```

## Test Files

| File | Tests | Description |
|------|-------|-------------|
| `unit/test_task_manager.py` | 30 | TaskManager unit tests (enqueue, claim, complete, fail, cancel) |
| `unit/test_risk_service.py` | 34 | RiskStateRepository tests (kill switch, P&L, exposure, limits) |
| `integration/test_health_api.py` | 15 | Health API endpoints (health, ready, live) |
| `integration/test_database.py` | 18 | Database initialization and table structure |
| **Total** | **87** | **Comprehensive test coverage** |

## Common Issues

### Import Errors
```bash
# Run from project root, not backend directory
cd E:\Personal\GitHub\good-signal
pytest backend/tests/
```

### Database Lock
```bash
# Clean up any lingering test databases
rm -f /tmp/*/test_good_signal.db
```

### Coverage Report
```bash
# Generate HTML coverage report
pytest backend/tests/ --cov=backend --cov-report=html
# Open htmlcov/index.html in browser
```

## Test Categories

- **Unit Tests (64 tests)**: Isolated component testing with mocks
  - TaskManager: 30 tests
  - RiskStateRepository: 34 tests

- **Integration Tests (23 tests)**: Multi-component and API testing
  - Health API: 15 tests
  - Database: 18 tests

## CI/CD

Tests are configured to run automatically in CI/CD pipelines with:
- Minimum 80% code coverage requirement
- Parallel test execution
- Coverage reports in XML format

See `backend/tests/README.md` for detailed documentation.
