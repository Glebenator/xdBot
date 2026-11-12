FROM denoland/deno:bin-2.9.5 AS deno
FROM python:3.11-slim AS build

RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 bot && \
    useradd --uid 1000 --gid bot --no-create-home bot && \
    install -d -o bot -g bot /app/data

COPY --from=build /opt/venv /opt/venv
COPY --from=deno /deno /usr/local/bin/deno
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DENO_DIR=/tmp/deno \
    MPLCONFIGDIR=/tmp/matplotlib \
    XDBOT_READY_FILE=/tmp/xdbot-ready

LABEL org.opencontainers.image.source="https://github.com/Glebenator/xdBot"

WORKDIR /app
COPY main.py config.py ./
COPY cogs/ cogs/
COPY utils/ utils/
COPY data/replies.json defaults/replies.json

USER bot
CMD ["python", "main.py"]
