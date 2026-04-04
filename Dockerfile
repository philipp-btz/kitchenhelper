# Use a lightweight Python image
FROM python:3.14.3-slim

LABEL authors="philipp"

# Set the working directory inside the container
WORKDIR /app

COPY . .

# install uv
RUN pip install uv

# Install dependencies
RUN uv sync




# Expose the port Gunicorn will run on
EXPOSE 80

# Command to run the app
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:80", "wsgi:application"]