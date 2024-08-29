## Run the flask app without docker

create a python virtual environment and activate it

```bash
python -m venv ./venv
source ./venv/bin/activate
```

install dependencies

```bash
pip install -r requirements.txt
```

Now run the app!

```bash
flask --app app run
```

## Run in a container with docker

Install docker https://www.docker.com/

```bash
docker compose up
```

This will run the app on the PORT specified in `.env` (see `.env.example`) or use 5000 by default.

## ssh into the container

```bash
docker exec -it <container name> /bin/bash
```

## Run multiple servers

```bash
PORT=5000
docker compose run -d -p $PORT:$PORT --name indianpoker_$PORT -e PORT=$PORT flask
```

## Run the game engine or evaluator stand alone

Run evaluator/indianpokergame

```bash
python evaluator.py
python indianpoker.py
```