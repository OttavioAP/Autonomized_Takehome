FROM python:3.11-slim

ARG UID=1000
ARG GID=1000

RUN groupadd --gid "${GID}" appuser \
    && useradd --uid "${UID}" --gid "${GID}" --create-home appuser

WORKDIR /app

COPY pyproject.toml requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY . .
RUN pip install --no-cache-dir -e . --no-deps \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
