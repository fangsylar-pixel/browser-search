# Contributing to Browser Search MCP

We welcome contributions! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/fangsylar-pixel/browser-search-mcp.git
cd browser-search-mcp
pip install -e .
python -m playwright install chromium
```

## Code Style

- Use type hints for all public functions
- Follow PEP 8
- Add docstrings for all public APIs
- Keep functions focused and small

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_search.py -v
```

## Pull Request Process

1. Fork the repo
2. Create a feature branch
3. Write tests and code
4. Run all tests
5. Submit a PR

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
