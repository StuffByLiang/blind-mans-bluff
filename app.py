import logging
from pathlib import Path
from flask import Flask, request, send_from_directory, render_template, redirect, url_for
from evaluator import ThreePlayerEvaluator
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

APP_TITLE = os.getenv("APP_TITLE") or "Indian Poker"
APP_DESCRIPTION = os.getenv("APP_DESCRIPTION") or "Made with love by Liang, Jeffrey, Matt"

########## Helpers ##########

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def common_context():
    return {
        "app_title": APP_TITLE,
        "app_description": APP_DESCRIPTION,
        "evaluator_status": evaluator.get_status(),
    }

########## Routes ##########

@app.route("/")
def index():
    global_pnl = evaluator.get_global_pnl()
    sorted_pnl = sorted(global_pnl.items(), key=lambda x: x[1], reverse=True)
    return render_template("index.html",
        strategies=evaluator.strategies,
        num_matchups=len(evaluator.three_tuple_of_strategies),
        global_results=sorted_pnl if sorted_pnl else None,
        **common_context(),
    )

@app.route("/strategies")
def strategies_page():
    message = request.args.get("message", "")
    message_type = request.args.get("message_type", "")
    global_pnl = evaluator.get_global_pnl()
    strat_info = {}
    for sid in evaluator.strategies:
        strat_info[sid] = {
            "file": evaluator.strategy_files.get(sid, "?"),
            "pnl": global_pnl.get(sid),
        }
    return render_template("strategies.html",
        strategies=strat_info,
        message=message,
        message_type=message_type,
        **common_context(),
    )

@app.route("/strategies/<strategy_id>/delete", methods=["POST"])
def delete_strategy(strategy_id):
    error = evaluator.delete_strategy(strategy_id)
    if error:
        return redirect(url_for("strategies_page", message=error, message_type="error"))
    return redirect(url_for("strategies_page", message=f"Deleted {strategy_id}", message_type="success"))

@app.route("/results")
def results():
    global_pnl = evaluator.get_global_pnl()
    sorted_results = sorted(
        [(name, pnl, evaluator.number_of_rounds_for_strategy.get(name, 0)) for name, pnl in global_pnl.items()],
        key=lambda x: x[1], reverse=True
    )

    matchups = []
    for strategies in evaluator.three_tuple_of_strategies:
        matchup_pnl = evaluator.get_matchup_pnl(strategies)
        matchups.append({
            "key": ",".join(strategies),
            "names": ", ".join(strategies),
            "results": sorted(matchup_pnl.items(), key=lambda x: x[1], reverse=True),
        })

    return render_template("results.html",
        global_results=sorted_results if sorted_results else None,
        matchups=matchups,
        **common_context(),
    )

@app.route("/results/<comma_separated_strategies>")
def results_detail(comma_separated_strategies: str):
    sorted_three_tuple = tuple(sorted(comma_separated_strategies.split(',')))
    key = ",".join(sorted_three_tuple)
    folder_path = Path(f"results/{key}")

    matchup_pnl = evaluator.get_matchup_pnl(sorted_three_tuple)
    sorted_results = sorted(
        [(name, pnl, evaluator.number_of_rounds_for_three_tuple[sorted_three_tuple].get(name, 0))
         for name, pnl in matchup_pnl.items()],
        key=lambda x: x[1], reverse=True
    )

    images = []
    if folder_path.exists():
        images = sorted([f.name for f in folder_path.glob('*.png')])

    return render_template("results_detail.html",
        names=", ".join(sorted_three_tuple),
        key=key,
        results=sorted_results,
        images=images,
        **common_context(),
    )

@app.route("/getstate/<strategy_id>")
def get_state(strategy_id):
    strategy = evaluator.strategies.get(strategy_id)
    if strategy is None:
        return render_template("state.html", strategy_id=strategy_id, state="Strategy not found", **common_context())
    return render_template("state.html", strategy_id=strategy_id, state=strategy.print_state(), **common_context())

@app.route("/interesting")
def interesting_games():
    matchups = []
    for strategies in evaluator.three_tuple_of_strategies:
        matchups.append({
            "key": ",".join(strategies),
            "names": ", ".join(strategies),
        })
    return render_template("interesting.html", matchups=matchups, **common_context())

@app.route("/interesting/<comma_separated_strategies>")
def interesting_game_detail(comma_separated_strategies: str):
    sorted_three_tuple = tuple(sorted(comma_separated_strategies.split(',')))

    rounds_list = []
    if sorted_three_tuple in evaluator.last_game:
        interesting_round_logs = []
        for round_num, round_history in enumerate(evaluator.last_game[sorted_three_tuple].round_history):
            round_state, log = round_history
            if not all(action.action_type == "check" for action in round_state.betting_history):
                interesting_round_logs.append((round_num, log))

        if interesting_round_logs:
            sample_size = 10
            random.shuffle(interesting_round_logs)
            rounds_list = sorted(interesting_round_logs[:sample_size], key=lambda x: x[0])

    return render_template("interesting_detail.html",
        names=", ".join(sorted_three_tuple),
        rounds=rounds_list,
        **common_context(),
    )

# add results as a public folder
@app.route('/resultspublic/<path:path>')
def send_results(path):
    return send_from_directory('results', path)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    message = ""
    message_type = ""
    if request.method == 'POST':
        if 'file' not in request.files:
            message, message_type = 'No file part', 'error'
        else:
            file = request.files['file']
            if file.filename == '':
                message, message_type = 'No selected file', 'error'
            elif not allowed_file(file.filename):
                message, message_type = 'Only .py files are allowed', 'error'
            else:
                filename = file.filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                evaluator.restart()
                if evaluator.load_errors:
                    message = 'File uploaded but errors occurred: ' + '; '.join(evaluator.load_errors)
                    message_type = 'error'
                else:
                    message, message_type = 'Strategy uploaded successfully', 'success'

    return render_template("upload.html", message=message, message_type=message_type, **common_context())

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
