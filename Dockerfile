# 1. Use the lightweight Python image as a base
FROM python:3.10-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Install necessary system tools
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy the requirements file into the container
COPY requirements.txt .

# 5. Install the required libraries
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy all project code (app.py, stellar_logic.py, etc.) into the container
COPY . .

# 7. Expose Port 8501 used by Streamlit
EXPOSE 8501

# 8. Command to run the app when the container starts
# --server.address=0.0.0.0 allows external access over the cloud
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
