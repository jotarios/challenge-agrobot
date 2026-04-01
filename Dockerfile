FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir . psycopg2-binary

COPY src/ src/
COPY simulator/ simulator/
COPY scripts/ scripts/
COPY alembic/ alembic/
COPY alembic.ini .

RUN chmod +x scripts/entrypoint.sh

ENTRYPOINT ["sh", "scripts/entrypoint.sh"]
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
