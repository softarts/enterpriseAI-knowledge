# Repository Development Instructions

## Python runtime compatibility

The supported Python runtime is Python 3.9.

- All new and modified Python code must be compatible with Python 3.9.
- Do not introduce Python 3.10+ syntax or runtime-only features, including PEP 604
  union annotations such as `str | None`. Use `Optional`, `Union`, `List`, `Dict`,
  `Tuple`, and related `typing` forms where appropriate.
- Do not rely on dependencies or APIs that require a newer Python version unless
  the project explicitly changes its supported runtime.
- Validate Python changes with the repository's Python 3.9 interpreter using
  `python3.9 -m py_compile ...` or an equivalent Python 3.9 check.

This compatibility rule applies to all services and CLI modules in this repository.
