# Use Playwright image that already bundles browsers (recommended)
FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

# copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy app
COPY . /app

# ensure python output is unbuffered (logs show in Render)
ENV PYTHONUNBUFFERED=1
# Use PORT env variable Render provides
ENV PORT=8080

EXPOSE 8080

# Run the flask app (app.py should respect $PORT environment variable)
CMD ["python", "app.py"]
