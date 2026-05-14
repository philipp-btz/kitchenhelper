FROM python:3.11-slim

LABEL authors="philipp"

WORKDIR /app

COPY . .

RUN pip install uv
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
