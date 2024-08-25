import logging
from flask import Flask, request, send_from_directory
from evaluator import Evaluator
from threading import Thread
from indianpoker import simulate_game
from io import StringIO
import os

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

########## Run Once ##########
UPLOAD_FOLDER = 'strategies'
ALLOWED_EXTENSIONS = {'py'}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# create a logger that is of INFO that only logs to a file
logger = logging.getLogger("Evaluator")
if not os.path.exists('logs'):
    os.makedirs('logs')
handler = logging.FileHandler('logs/evaluator.log', mode='w+')
handler.setFormatter(logging.Formatter('%(message)s'))
handler.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

evaluator = Evaluator(logger)
def run_evaluator():
    evaluator.load_strategies()
    evaluator.evaluate_strategies()
Thread(target=run_evaluator).start()

########## Helpers ##########

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

########## Routes ##########

@app.route("/")
def hello_world():
    strategies = evaluator.strategies
    return f"""
    <h1>Indian Poker Strategy Evaluator</h1>
    <p>Upload your strategies to see how they perform against each other</p>
    <a href="/results">View Results</a> <br />
    <a href="/examplegame">View Example Game</a> <br />
    <a href="/upload">Upload New Strategy</a> <br />
    Current strategies: {list(strategies.keys())}
    """

@app.route("/results")
def results():
    try:
        with open('results/results.txt', 'r') as f:
            # read the last 3 lines
            lines = f.readlines()[-3:]

            results = "<h1>Results</h1>"
            for line in lines:
                results += f"<p>{line}</p>"

            # now get all pngs in results folder and display them
            images = ""
            for file in os.listdir('results'):
                if file.endswith('.png'):
                    images += f'<img src="results/{file}" width="500" />'
                
            return results + images
    except FileNotFoundError:
        return "No results yet"

@app.route("/examplegame")
def example_game():
    logger = logging.getLogger("ExampleGame")
    logger.setLevel(logging.DEBUG)

    # get print of logger to a string
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.setLevel(logging.DEBUG)

    logger.addHandler(handler)
    logger.propagate = False

    simulate_game(evaluator.strategies, 5, 200, 1, logger)

    # now grab logs from the logger
    logs = log_stream.getvalue()
    logs = "<br />".join(logs.split('\n'))
    return logs
    
# add results as a public folder
@app.route('/results/<path:path>')
def send_results(path):
    return send_from_directory('results', path)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            return 'No file part'
        
        file = request.files['file']
        
        # If user does not select file, browser also
        # submits an empty part without filename
        if file.filename == '':
            return 'No selected file'
        
        if file and allowed_file(file.filename):
            filename = file.filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            evaluator.stop()
            evaluator.load_strategies()
            evaluator.evaluate_strategies()
            return 'File successfully uploaded'
    
    return '''
    <!doctype html>
    <title>Upload File</title>
    <h1>Upload new File</h1>
    <form method="post" enctype="multipart/form-data" action="/upload">
      <input type="file" name="file">
      <input type="submit" value="Upload">
    </form>
    '''

if __name__ == "__main__":
    app.run(debug=True)
