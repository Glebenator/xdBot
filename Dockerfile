# Start with a base image that has Python 3.11 installed
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies needed to build Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy your requirements.txt file into the container
COPY requirements.txt .

# Install your Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your bot files into the container
COPY . .

# Specify the command to run your bot
CMD ["python", "main.py"]