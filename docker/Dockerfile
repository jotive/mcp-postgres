FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# MCP stdio server. Clients spawn this process and speak MCP over stdin/stdout.
# Provide MCPPG_TARGETS (a read-only DSN) at runtime.
ENTRYPOINT ["mcp-postgres"]
