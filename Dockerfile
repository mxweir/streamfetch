FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY app.py ./
COPY docs/assets/streamfetch-mark.svg ./docs/assets/streamfetch-mark.svg
RUN python -m pip install --upgrade pip && pip install .

COPY app.py ./
COPY .streamlit ./.streamlit

RUN useradd --create-home --uid 10001 streamfetch \
    && mkdir -p /app/downloads \
    && chown -R streamfetch:streamfetch /app
USER streamfetch

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
