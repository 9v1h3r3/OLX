# ✅ Use the exact Playwright version that matches your library (1.55.0)
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# Set working directory
WORKDIR /app

# Copy dependency list and install them
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# ✅ Ensure browsers are properly installed
RUN playwright install --with-deps chromium

# Copy all project files
COPY . /app

# Make sure Python output is visible in Render logs
ENV PYTHONUNBUFFERED=1
# Render injects PORT automatically
ENV PORT=8080

EXPOSE 8080

# ✅ Start the app
CMD ["python", "app.py"]
