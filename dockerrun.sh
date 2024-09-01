# SUDO=sudo # comment out if dont want sudo
PORT=42069 STRATEGIES_DIR=~/strategies1 && $SUDO docker compose run -d \
    -v $STRATEGIES_DIR:/app/strategies \
    -p $PORT:$PORT \
    --name indianpoker_$PORT \
    -e PORT=$PORT \
    -e APP_TITLE="Beginner's Room" \
    -e APP_DESCRIPTION="This is the room for beginners. Please use the medium room if you are doing better." \
    flask

PORT=42070 STRATEGIES_DIR=~/strategies2 && $SUDO docker compose run -d \
    -v $STRATEGIES_DIR:/app/strategies \
    -p $PORT:$PORT \
    --name indianpoker_$PORT \
    -e PORT=$PORT \
    -e APP_TITLE="Intermediate Room" \
    -e APP_DESCRIPTION="This is the room for intermediates. Please use the pro room if you are doing better." \
    flask

PORT=42071 STRATEGIES_DIR=~/strategies3 && $SUDO docker compose run -d \
    -v $STRATEGIES_DIR:/app/strategies \
    -p $PORT:$PORT \
    --name indianpoker_$PORT \
    -e PORT=$PORT \
    -e APP_TITLE="Pro" \
    -e APP_DESCRIPTION="This is the room for pros. You're probably a goat if you're here. If not, we believe in you! start in the beginner and intermediate rooms." \
    flask