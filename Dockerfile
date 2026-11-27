FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# stdio MCP server (wrapper over the same tool functions) — mount a key file or pass --key
CMD ["python3", "mcp_stdio.py"]
