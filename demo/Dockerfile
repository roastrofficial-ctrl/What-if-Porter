FROM python:3.12-alpine

WORKDIR /demo
COPY pyproject.toml ./
COPY porter ./porter
RUN pip install --no-cache-dir .
COPY demo/service.py ./service.py

ENTRYPOINT ["python", "service.py"]
