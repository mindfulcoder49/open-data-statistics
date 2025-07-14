# Use an official Python image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the FastAPI app files
COPY . .

# Expose port 8080 for the FastAPI app
EXPOSE 8080

# The default command is to run the FastAPI app.
# The worker command is specified in docker-compose.dev.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]