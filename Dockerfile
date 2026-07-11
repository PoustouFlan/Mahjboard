FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p instance

EXPOSE 5000

# -w 4: Use 4 worker processes
# -b 0.0.0.0:5000: Bind to all interfaces on port 5000
# run:app : Look in 'run.py' for the 'app' object
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app"]
