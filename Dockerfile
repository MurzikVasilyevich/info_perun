# syntax=docker/dockerfile:1
FROM python:3.8-slim-buster
WORKDIR /app

RUN apt-get update && apt-get install -y

RUN pip3 install psycopg2-binary

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
COPY . .
CMD ["python", "app.py"]