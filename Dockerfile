FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY scripts/ scripts/
COPY alembic/ alembic/
COPY alembic.ini .

ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
