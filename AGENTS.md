# Repository Development Instructions

## Python runtime compatibility

The supported Python runtime is Python 3.14.

- All new and modified Python code must be compatible with Python 3.14.
- Use the virtual environment at the repository root (`.venv-py314`) for all
  installs and test runs; the Homebrew interpreter is PEP 668 protected and
  will refuse direct `pip install`.
- Run tests with `.venv-py314/bin/python -m unittest ...` from the repository root.
- langchain-core 1.x / langgraph 1.x are required for the streaming chat
  endpoints; earlier LangGraph releases do not support custom stream writers.

```bash
.venv-py314/bin/python -m py_compile path/to/module.py
.venv-py314/bin/python -m unittest discover -s <module>/tests -t .
```

## Test placement

- Keep tests under the `test/` or `tests/` directory of the module they test.
- Do not create or use a repository-root `test/` or `tests/` directory for new tests.
- Run module tests from the repository root using their module-relative path.
