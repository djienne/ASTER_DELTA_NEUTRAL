# Python 3.12: 3.9 reached end of life in October 2025 and stopped receiving
# security fixes. web3/eth-account pull a large transitive tree, so running the
# signing path on an unpatched interpreter is not a theoretical concern.
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code to the working directory
COPY . .

# Writable state (halt sentinel). docker-compose mounts a host volume over this;
# creating it here keeps `docker run` without compose working too.
RUN mkdir -p /app/data
ENV ASTER_DN_DATA_DIR=/app/data

# Specify the command to run on container startup
CMD ["python", "delta_neutral_bot.py"]
