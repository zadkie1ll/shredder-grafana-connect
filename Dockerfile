FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

FROM python:3.12-slim
RUN groupadd --system app && useradd --system --gid app --home /app app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app ./app
RUN mkdir -p /app/data /prometheus-targets && chown -R app:app /app/data /prometheus-targets
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
