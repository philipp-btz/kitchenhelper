# Use a lightweight Python image
FROM python:3.11-slim

LABEL authors="philipp"

# Set the working directory inside the container
WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy the rest of the application code
COPY . .

# Expose the port Gunicorn will run on
EXPOSE 80

# Command to run the app
CMD ["gunicorn", "--bind", "0.0.0.0:80", "wsgi:application"]