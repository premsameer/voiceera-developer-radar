FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY radar radar
COPY dashboard.py .
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data
EXPOSE 8000 8501
CMD ["uvicorn","radar.api:app","--host","0.0.0.0","--port","8000"]

