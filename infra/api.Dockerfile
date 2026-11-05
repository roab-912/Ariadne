FROM python:3.12.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY apps/api ./apps/api
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir --no-deps . && useradd --create-home ariadne
USER ariadne
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
