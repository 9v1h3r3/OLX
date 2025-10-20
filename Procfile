# Dockerfile - small image with headless chromium + python
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install chromium and chromedriver + minimal deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    ca-certificates \
    fonts-liberation \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY send_min.py /app/
COPY start.sh /app/

# ensure chrome binary is in PATH for selenium to auto-detect
ENV CHROME_BIN=/usr/bin/chromium
ENV DISPLAY=:99

RUN chmod +x /app/start.sh

# default command
CMD ["/app/start.sh"]
