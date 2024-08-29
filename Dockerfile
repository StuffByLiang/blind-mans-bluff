FROM python:3.12-slim-bookworm

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD gunicorn -w 1 -b 0.0.0.0:$PORT app:app