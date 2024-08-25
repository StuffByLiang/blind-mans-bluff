import logging
from flask import Flask, request, send_from_directory
from evaluator import Evaluator
from threading import Thread
import os

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

########## Run Once ##########
UPLOAD_FOLDER = 'strategies'
ALLOWED_EXTENSIONS = {'py'}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


class EvaluatorWrapper():
    def __init__(self):
        super().__init__()
        self.thread = None
        self.evaluator = None
    
    def run(self):
        # create a logger that is of INFO that only logs to a file
        logger = logging.getLogger("Evaluator")
        if not os.path.exists('logs'):
            os.makedirs('logs')
        handler = logging.FileHandler('logs/evaluator.log', mode='w+')
        handler.setFormatter(logging.Formatter('%(message)s'))
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        self.evaluator = Evaluator(logger)
        self.evaluator.load_strategies()

        thread = Thread(target=self.evaluator.evaluate_strategies)
        thread.start()

    def restart(self):
        if self.thread:
            evaluator_wrapper.stop = True
            self.thread.join()
        self.run()

evaluator_wrapper = EvaluatorWrapper()
evaluator_wrapper.restart()

########## Helpers ##########

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

########## Routes ##########

@app.route("/")
def hello_world():
    strategies = evaluator_wrapper.evaluator.strategies
    return f"""
    <h1>Indian Poker Strategy Evaluator</h1>
    <p>Upload your strategies to see how they perform against each other</p>
    <a href="/results">View Results</a> <br />
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
            evaluator_wrapper.restart()
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
