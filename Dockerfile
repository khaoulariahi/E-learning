# One image for the worker and the Streamlit dev UI (docker compose picks the command).
# System packages needed by later phases go here: ffmpeg (Phase 4), Chromium for Playwright (Phase 5).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ASSISTANT_DATA_DIR=/app/data

WORKDIR /app

COPY assistant/requirements.lock.txt assistant/requirements.lock.txt
RUN pip install -r assistant/requirements.lock.txt

COPY pytest.ini ./
COPY assistant ./assistant

EXPOSE 8501
CMD ["python", "-m", "assistant.worker"]
