FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd --system runner \
    && useradd --system --gid runner --create-home --home-dir /home/runner runner

WORKDIR /sandbox

USER runner

CMD ["python", "-I", "-c", "import time; print('code-runner ready', flush=True); time.sleep(31536000)"]
