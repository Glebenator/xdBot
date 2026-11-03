# Build stage: install the Python dependencies into a virtual environment.
# gcc is only here, for any dependency without a prebuilt wheel.
FROM python:3.11-slim AS build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage: the virtual environment, the bot, and the system libraries it
# needs (FFmpeg for music, libGL and GLib for OpenCV and MediaPipe).
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user. The IDs match the usual first user on a Linux
# host, so a bind-mounted ./data stays writable; override them with build args.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "$GID" bot && useradd --uid "$UID" --gid bot --no-create-home bot

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .
# The bot writes its database, replies and word filter to data/.
RUN mkdir -p data && chown -R bot:bot data

USER bot
CMD ["python", "main.py"]
