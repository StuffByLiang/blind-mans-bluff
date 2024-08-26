import logging
from pathlib import Path
from flask import Flask, request, send_from_directory
from evaluator import ThreePlayerEvaluator
from threading import Thread
import os
import random

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

if os.getenv('VERBOSE'):
    print("Verbose mode enabled")
    handler.setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    handler.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

evaluator = ThreePlayerEvaluator(logger)
evaluator.load_strategies()
evaluator.start_evaluating_strategies()

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
    <a href="/results">View Global Results</a> <br />
    <a href="/exampleinterestinggame">View Example Interesting Games</a> <br />
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
            
            for strategies in evaluator.three_tuple_of_strategies:
                results += f'<a href="/results/{",".join(strategies)}">Results for {", ".join(strategies)}</a><br />'
                
            return results
    except FileNotFoundError:
        return "No results yet"

@app.route("/results/<comma_separated_strategies>")
def results_per_comma_separated_strategy(comma_separated_strategies: str):
    sorted_three_tuple = tuple(sorted(comma_separated_strategies.split(',')))
    folder_name = ",".join(sorted_three_tuple)
    folder_path = Path(f"results/{folder_name}")
    # now get all pngs in results folder and display them
    images = ""
    try:
        with open(folder_path / 'results.txt', 'r') as f:
            # read the last 3 lines
            lines = f.readlines()[-3:]

            results = f"<h1>Results for {sorted_three_tuple}</h1>"
            for line in lines:
                results += f"<p>{line}</p>"

            for file in folder_path.glob('*.png'):
                images += f'<img src="/resultspublic/{comma_separated_strategies}/{file.name}" alt="{file.name}" width="500">'
            
            results += images
            return results
    except FileNotFoundError:
        return f"No results yet for {sorted_three_tuple}"

@app.route("/getstate/<strategy>")
def get_state(strategy):
    strategy = evaluator.strategies.get(strategy)
    if strategy is None:
        return "Strategy not found"
    return strategy.print_state()

@app.route("/exampleinterestinggame")
def example_interesting_game():
    results = "<h1>Find Example Interesting Games</h1>"
    for strategies in evaluator.three_tuple_of_strategies:
        results += f'<a href="/exampleinterestinggame/{",".join(strategies)}">Example Interesting Game for {", ".join(strategies)}</a><br />'

    return results
    
    
@app.route("/exampleinterestinggame/<comma_separated_strategies>")
def example_interesting_game_for_strategies(comma_separated_strategies: str):
    sorted_three_tuple = tuple(sorted(comma_separated_strategies.split(',')))

    if sorted_three_tuple in evaluator.last_game:
        interesting_round_logs: list[tuple[int, str]] = [] # [(round_num, log)]
        for round_num, round_history in enumerate(evaluator.last_game[sorted_three_tuple].round_history):
            round, log = round_history 
            if not all(action.action_type == "check" for action in round.betting_history):
                interesting_round_logs.append((round_num, log))
            
        if len(interesting_round_logs) == 0:
            return "No interesting rounds found"
        # now sample 10 random interesting_round logs but make sure to keep them in order
        sample_size = 10
        random.shuffle(interesting_round_logs)
        interesting_round_logs = sorted(interesting_round_logs[:sample_size], key=lambda x: x[0])
        html = ""
        for round_num, logs in interesting_round_logs:
            html += f"<b>Round {round_num}</b><p style='white-space: pre-wrap'>{logs}</p>"
        return html
    else:
        return "No results found"
    
# add results as a public folder
@app.route('/resultspublic/<path:path>')
def send_results(path):
    return send_from_directory('results', path)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    error_msg = ""
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            error_msg = 'No file part'
        
        file = request.files['file']
        
        # If user does not select file, browser also
        # submits an empty part without filename
        if file.filename == '':
            error_msg = 'No selected file'
        
        if file and allowed_file(file.filename):
            filename = file.filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            evaluator.restart()
            error_msg = 'File successfully uploaded'
    
    return f'''
    <!doctype html>
    <title>Upload File</title>
    <p style="color:red">{error_msg}</p>
    <h1>Upload new File</h1>
    <form method="post" enctype="multipart/form-data" action="/upload">
      <input type="file" name="file">
      <input type="submit" value="Upload">
    </form>
    '''

if __name__ == "__main__":
    app.run(debug=True)
