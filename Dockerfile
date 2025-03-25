FROM python:3.10-slim

ENV PYTHONPATH=/app


WORKDIR /app
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt


EXPOSE 5000

CMD ["python", "server/main/app.py"]
