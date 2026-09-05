FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY geoflow ./geoflow
COPY web ./web
RUN pip install --no-cache-dir .

EXPOSE 8765
CMD ["uvicorn", "geoflow.api:app", "--host", "0.0.0.0", "--port", "8765"]
