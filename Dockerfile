FROM python:3.12-alpine
WORKDIR /porter
COPY pyproject.toml ./
COPY porter ./porter
RUN pip install --no-cache-dir . && mkdir -p /ipc
EXPOSE 7070
ENTRYPOINT ["porter"]
