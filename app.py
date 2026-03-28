import logging
import io
from pathlib import Path
from flask import Flask, request, send_from_directory, render_template, redirect, url_for, jsonify, Response
from evaluator import ThreePlayerEvaluator
import os
import random
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

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
        num_matchups=len(evaluator.three_tuple_of_strategies) + len(evaluator.two_tuple_of_strategies),
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

@app.route("/reset", methods=["POST"])
def reset():
    evaluator.restart()
    return redirect(url_for("index"))

@app.route("/results")
def results():
    global_pnl = evaluator.get_global_pnl()
    sorted_results = sorted(
        [(name, pnl, evaluator.number_of_rounds_for_strategy.get(name, 0)) for name, pnl in global_pnl.items()],
        key=lambda x: x[1], reverse=True
    )

    matchups_3p = []
    for strategies in evaluator.three_tuple_of_strategies:
        matchup_pnl = evaluator.get_matchup_pnl(strategies)
        matchups_3p.append({
            "key": ",".join(strategies),
            "names": ", ".join(strategies),
            "results": sorted(matchup_pnl.items(), key=lambda x: x[1], reverse=True),
        })

    matchups_1v1 = []
    for strategies in evaluator.two_tuple_of_strategies:
        matchup_pnl = evaluator.get_matchup_pnl(strategies)
        matchups_1v1.append({
            "key": ",".join(strategies),
            "names": ", ".join(strategies),
            "results": sorted(matchup_pnl.items(), key=lambda x: x[1], reverse=True),
        })

    return render_template("results.html",
        global_results=sorted_results if sorted_results else None,
        matchups_3p=matchups_3p,
        matchups_1v1=matchups_1v1,
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
    if strategy.state_password is not None:
        pw = request.args.get("password", "")
        if pw != strategy.state_password:
            return render_template("state.html", strategy_id=strategy_id, state="Password required. Add ?password=... to URL", **common_context())
    return render_template("state.html", strategy_id=strategy_id, state=strategy.print_state(), **common_context())

@app.route("/interesting")
def interesting_games():
    matchups_3p = []
    for strategies in evaluator.three_tuple_of_strategies:
        matchups_3p.append({
            "key": ",".join(strategies),
            "names": ", ".join(strategies),
        })
    matchups_1v1 = []
    for strategies in evaluator.two_tuple_of_strategies:
        matchups_1v1.append({
            "key": ",".join(strategies),
            "names": ", ".join(strategies),
        })
    return render_template("interesting.html", matchups_3p=matchups_3p, matchups_1v1=matchups_1v1, **common_context())

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

########## JSON API ##########

@app.route("/api/state/<strategy_id>")
def api_state(strategy_id):
    strategy = evaluator.strategies.get(strategy_id)
    if strategy is None:
        return jsonify({"error": f"Strategy {strategy_id} not found"}), 404
    if strategy.state_password is not None:
        pw = request.args.get("password", "")
        if pw != strategy.state_password:
            return jsonify({"error": "Password required", "hint": "Add ?password=..."}), 403
    return jsonify({"strategy_id": strategy_id, "state": strategy.print_state()})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only .py files allowed"}), 400
    filename = file.filename
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    evaluator.restart()
    if evaluator.load_errors:
        return jsonify({"status": "error", "errors": evaluator.load_errors}), 400
    return jsonify({"status": "ok", "message": f"Uploaded {filename}, evaluator restarted"})

@app.route("/api/results")
def api_results():
    global_pnl = evaluator.get_global_pnl()
    # Include per-matchup results (both 3-player and 1v1)
    matchups = {}
    all_tuples = set(evaluator.pnl_for_three_tuple.keys())
    for strat_tuple in all_tuples:
        key = ",".join(strat_tuple)
        matchups[key] = evaluator.get_matchup_pnl(strat_tuple)
    return jsonify({
        "global_pnl": global_pnl,
        "rounds": dict(evaluator.number_of_rounds_for_strategy),
        "num_evaluations": evaluator.num_evaluations,
        "matchups": matchups,
    })

@app.route("/api/interesting/<comma_separated_strategies>")
def api_interesting(comma_separated_strategies: str):
    sorted_three_tuple = tuple(sorted(comma_separated_strategies.split(',')))
    rounds_list = []
    if sorted_three_tuple in evaluator.last_game:
        for round_num, round_history in enumerate(evaluator.last_game[sorted_three_tuple].round_history):
            round_state, log = round_history
            if not all(action.action_type == "check" for action in round_state.betting_history):
                actions = []
                for a in round_state.betting_history:
                    actions.append({
                        "player": a.player_id,
                        "type": a.action_type,
                        "delta": a.delta,
                    })
                cards = {}
                for p in round_state.player_information.values():
                    cards[p.player_id] = p.card
                rounds_list.append({
                    "round": round_num,
                    "cards": cards,
                    "actions": actions,
                    "pot": round_state.pot,
                    "log": log,
                })
    return jsonify({"matchup": list(sorted_three_tuple), "interesting_rounds": rounds_list})

@app.route("/api/interesting_all/<comma_separated_strategies>")
def api_interesting_all(comma_separated_strategies: str):
    """Return ALL round data (not just interesting) from last game for deep analysis."""
    sorted_three_tuple = tuple(sorted(comma_separated_strategies.split(',')))
    rounds_list = []
    if sorted_three_tuple in evaluator.last_game:
        for round_num, round_history in enumerate(evaluator.last_game[sorted_three_tuple].round_history):
            round_state, log = round_history
            actions = []
            for a in round_state.betting_history:
                actions.append({
                    "player": a.player_id,
                    "type": a.action_type,
                    "delta": a.delta,
                })
            cards = {}
            for p in round_state.player_information.values():
                cards[p.player_id] = p.card
            rounds_list.append({
                "round": round_num,
                "cards": cards,
                "actions": actions,
                "pot": round_state.pot,
            })
    return jsonify({"matchup": list(sorted_three_tuple), "total_rounds": len(rounds_list), "rounds": rounds_list})

@app.route("/api/heatmap/<strategy_id>")
def api_heatmap(strategy_id):
    """Generate a 52x52 heatmap PNG of card matchup PnL."""
    strategy = evaluator.strategies.get(strategy_id)
    if strategy is None:
        return jsonify({"error": f"Strategy {strategy_id} not found"}), 404
    if strategy.state_password is not None:
        pw = request.args.get("password", "")
        if pw != strategy.state_password:
            return jsonify({"error": "Password required"}), 403

    opp = request.args.get("opp", "")
    pos = int(request.args.get("pos", 0))
    pos_label = "we pay ante" if pos == 1 else "they pay ante"

    if not hasattr(strategy, 'card_matchup_pnl'):
        return jsonify({"error": "No card matchup data"}), 404

    # Build 52x52 matrix
    grid = np.full((52, 52), np.nan)
    n_filled = 0
    for (oid, mc, oc, p), (total, count) in strategy.card_matchup_pnl.items():
        if oid == opp and p == pos and count > 0:
            grid[mc][oc] = total / count
            n_filled += 1

    # Use OO API only — never touch plt — to avoid race with evaluator's plotting thread
    fig = Figure(figsize=(14, 12))
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    if n_filled == 0:
        ax.text(0.5, 0.5, 'No data yet', transform=ax.transAxes, ha='center', va='center', fontsize=20)
    else:
        display_grid = np.where(np.isnan(grid), 0, grid)
        mask = np.isnan(grid)
        vmax = min(float(np.nanmax(np.abs(grid[~np.isnan(grid)]))), 8)
        vmax = max(vmax, 1)

        im = ax.imshow(display_grid, cmap='RdYlGn', vmin=-vmax, vmax=vmax,
                        aspect='equal', interpolation='nearest', origin='upper')
        # Gray out cells with no data
        overlay = np.zeros((*grid.shape, 4))
        overlay[mask] = [0.2, 0.2, 0.2, 1.0]
        ax.imshow(overlay, aspect='equal', interpolation='nearest', origin='upper')

        fig.colorbar(im, ax=ax, label='Avg PnL per round', shrink=0.8)

    rank_labels = ['A','2','3','4','5','6','7','8','9','10','J','Q','K']
    tick_pos = [i * 4 + 1.5 for i in range(13)]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(rank_labels, fontsize=9)
    ax.set_yticks(tick_pos)
    ax.set_yticklabels(rank_labels, fontsize=9)

    for i in range(1, 13):
        ax.axhline(i * 4 - 0.5, color='white', linewidth=0.5, alpha=0.7)
        ax.axvline(i * 4 - 0.5, color='white', linewidth=0.5, alpha=0.7)

    ax.set_xlabel(f"Opponent card ({opp})", fontsize=12)
    ax.set_ylabel(f"Our card ({strategy_id})", fontsize=12)
    ax.set_title(f"PnL per round vs {opp} ({pos_label}) — {n_filled} cells filled\nGreen=profit, Red=loss, Gray=no data", fontsize=13)

    fig.tight_layout()
    buf = io.BytesIO()
    canvas.print_png(buf)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
