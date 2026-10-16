FROM python:3.13-slim

RUN pip install --no-cache-dir boto3==1.43.106

WORKDIR /spike
COPY . .

EXPOSE 8000
CMD ["python", "server.py"]
