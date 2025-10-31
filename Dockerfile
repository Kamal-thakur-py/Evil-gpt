# Use a lightweight, official Python image 
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your project files (including your main script)
COPY . .

# *** ADD THIS LINE ***
# Expose a common port. This satisfies the platform's requirement 
# for a running "Web App" or "Container" for long polling bots.
EXPOSE 80 
# ********************

# The command to execute your bot script when the container starts.
CMD ["python", "stdiffusionop.py"]
