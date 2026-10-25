# LLM Guardrail Gateway

A security proxy for LLM APIs. It detects prompt injection, redacts personal data and secrets, and audits every request.

> Work in progress: full documentation arrives in a later pull request.

## Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```
