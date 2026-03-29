# import all strategies from strategies folder and play mulitple rounds of indian poker
from collections import defaultdict
import threading
from indianpoker import RoundState, Strategy, IndianPokerGame, simulate_game
from importlib import reload
from pathlib import Path
import os
import json
import logging
import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('agg')
import itertools
import time

RESULTS_DIR = Path('results')

StrategyTuple = tuple[str, ...]

class ThreePlayerEvaluator:
    def __init__(self, logger = logging.getLogger(__name__)):
        self.logger = logger

        self.strategy_classes: dict[str, Strategy] = {}
        self.strategies: dict[str, Strategy] = {}
        self.strategy_files: dict[str, str] = {}  # player_id -> filename
        self.load_errors: list[str] = []  # errors from last load

        self.three_tuple_of_strategies: set[StrategyTuple] = set()
        self.two_tuple_of_strategies: set[StrategyTuple] = set()

        # used for running
        self.request_stop = False
        self.main_thread = None
        self.num_evaluations = 0
        self.is_running = False

    def reset(self):
        # used for global score
        self.pnl_for_strategy: dict[str, int] = defaultdict(int) # player_id -> number of chips
        self.number_of_rounds_for_strategy: dict[str, int] = defaultdict(int) # player_id -> number of games

        # used for individual scores
        self.pnl_for_three_tuple: dict[ThreeTupleOfStrategies, dict[str, int]] = defaultdict(lambda: defaultdict(int)) # sorted (strategy1, strategy2, strategy3) -> player_id -> number of games
        self.number_of_rounds_for_three_tuple: dict[ThreeTupleOfStrategies, dict[str, int]] = defaultdict(lambda: defaultdict(int)) # sorted (strategy1, strategy2, strategy3) -> player_id -> number of games
        self.last_game: dict[ThreeTupleOfStrategies, IndianPokerGame] = {} # sorted (strategy1, strategy2, strategy3) -> Game


    def load_strategies(self):
        self.strategies = {}
        self.strategy_files = {}
        self.load_errors = []
        for file in os.listdir('strategies'):
            if file.endswith('.py') and file != 'indianpoker.py':
                try:
                    strategy_module = __import__(f'strategies.{file[:-3]}', fromlist=[''])
                    reload(strategy_module)
                    strategy_class: Strategy = getattr(strategy_module, "strategy")
                    if not hasattr(strategy_class, 'player_id') or not strategy_class.player_id:
                        raise ValueError(f"Strategy in {file} has no player_id")
                    if not hasattr(strategy_class, 'make_decision'):
                        raise ValueError(f"Strategy in {file} has no make_decision method")
                    self.strategy_classes[strategy_class.player_id] = strategy_class
                    self.strategies[strategy_class.player_id] = strategy_class()
                    self.strategy_files[strategy_class.player_id] = file
                    self.logger.info(f"Loaded strategy {strategy_class.player_id} from file {file})")
                except Exception as e:
                    error_msg = f"Error loading {file}: {e}"
                    self.load_errors.append(error_msg)
                    self.logger.exception(f"Error loading strategy from file {file}")

        # pitch the strategies against each other
        self.logger.info(f"Reloaded Strategies: strategies playing: {self.strategies}")

        # Preserve existing matchups (only remove ones with deleted strategies)
        valid_ids = set(self.strategies.keys())
        self.three_tuple_of_strategies = {t for t in self.three_tuple_of_strategies if all(s in valid_ids for s in t)}
        self.two_tuple_of_strategies = {t for t in self.two_tuple_of_strategies if all(s in valid_ids for s in t)}

        self.reset()

        # remove all files from results folder and make it if needed
        if not RESULTS_DIR.exists():
            RESULTS_DIR.mkdir()
        for file in RESULTS_DIR.iterdir():
            if file.is_file():
                file.unlink()
            else: # remove all directories
                for f in file.iterdir():
                    f.unlink()
                file.rmdir()

    def restart(self):
        self.request_stop = True
        if self.main_thread is not None:
            self.main_thread.join()
        self.request_stop = False
        self.load_strategies()
        self.start_evaluating_strategies()
    
    def start_evaluating_strategies(self):
        self.main_thread = threading.Thread(target=self.run)
        self.main_thread.start()

    def add_matchup(self, player_ids: list[str]) -> str:
        """Add a matchup. Returns error message or empty string on success."""
        for pid in player_ids:
            if pid not in self.strategies:
                return f"Strategy '{pid}' not found"
        t = tuple(sorted(player_ids))
        if len(t) == 2:
            if t in self.two_tuple_of_strategies:
                return "Matchup already exists"
            self.two_tuple_of_strategies.add(t)
        elif len(t) == 3:
            if t in self.three_tuple_of_strategies:
                return "Matchup already exists"
            self.three_tuple_of_strategies.add(t)
        else:
            return "Matchup must have 2 or 3 players"
        return ""

    def remove_matchup(self, player_ids: list[str]) -> str:
        """Remove a matchup. Returns error message or empty string on success."""
        t = tuple(sorted(player_ids))
        if len(t) == 2:
            if t not in self.two_tuple_of_strategies:
                return "Matchup not found"
            self.two_tuple_of_strategies.discard(t)
        elif len(t) == 3:
            if t not in self.three_tuple_of_strategies:
                return "Matchup not found"
            self.three_tuple_of_strategies.discard(t)
        else:
            return "Matchup must have 2 or 3 players"
        return ""

    def delete_strategy(self, player_id: str) -> str:
        """Delete a strategy by player_id. Returns error message or empty string on success."""
        if player_id not in self.strategy_files:
            return f"Strategy '{player_id}' not found"
        filename = self.strategy_files[player_id]
        filepath = Path('strategies') / filename
        if filepath.exists():
            filepath.unlink()
        self.restart()
        return ""

    def get_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "num_evaluations": self.num_evaluations,
            "num_strategies": len(self.strategies),
            "num_matchups": len(self.three_tuple_of_strategies) + len(self.two_tuple_of_strategies),
        }

    def get_global_pnl(self) -> dict[str, float]:
        """Returns {player_id: avg_pnl_per_1000_rounds}."""
        result = {}
        for strategy in self.strategies:
            rounds = self.number_of_rounds_for_strategy.get(strategy, 0)
            if rounds > 0:
                result[strategy] = self.pnl_for_strategy[strategy] * 1000 / rounds
            else:
                result[strategy] = 0.0
        return result

    def get_matchup_pnl(self, sorted_three_tuple) -> dict[str, float]:
        """Returns {player_id: avg_pnl_per_1000_rounds} for a specific matchup."""
        result = {}
        for strategy in sorted_three_tuple:
            rounds = self.number_of_rounds_for_three_tuple[sorted_three_tuple].get(strategy, 0)
            if rounds > 0:
                result[strategy] = self.pnl_for_three_tuple[sorted_three_tuple][strategy] * 1000 / rounds
            else:
                result[strategy] = 0.0
        return result

    def run(self):
        ante=5
        starting_stack=200
        rounds=1000

        last_write_time = datetime.datetime.now()
        self.num_evaluations = 0
        self.is_running = True

        try:
          while True:
            all_matchups = list(self.three_tuple_of_strategies) + list(self.two_tuple_of_strategies)
            if not all_matchups:
                time.sleep(1)
                if self.request_stop:
                    return
                continue
            for sorted_strategy_tuple in all_matchups:
                if self.request_stop:
                    return
                game = simulate_game({k: v for k, v in self.strategies.items() if k in sorted_strategy_tuple}, ante, starting_stack, rounds)
                self.last_game[sorted_strategy_tuple] = game

                for strategy in sorted_strategy_tuple:
                    num_rounds_for_strategy = game.turn_busted[strategy] if strategy in game.turn_busted else len( game.round_history )
                    pnl = (game.stack_sizes[strategy] - starting_stack)

                    if len(sorted_strategy_tuple) == 3:
                        self.number_of_rounds_for_strategy[strategy] += num_rounds_for_strategy
                        self.pnl_for_strategy[strategy] += pnl

                    self.number_of_rounds_for_three_tuple[sorted_strategy_tuple][strategy] += num_rounds_for_strategy
                    self.pnl_for_three_tuple[sorted_strategy_tuple][strategy] += pnl

            if datetime.datetime.now() - last_write_time > datetime.timedelta(seconds=1):
                def write_global_results():
                    avg_pnl_per_1000_rounds = {}
                    for strategy in self.strategies:
                        avg_pnl_per_1000_rounds[strategy] = (self.pnl_for_strategy[strategy]) * 1000 / (self.number_of_rounds_for_strategy[strategy] if self.number_of_rounds_for_strategy[strategy] > 0 else 1)
                    self.logger.info(f"Average pnl per 1000 games: {avg_pnl_per_1000_rounds}")
                    with open('results/results.txt', 'a') as f:
                        results_json = {
                            "num_evaluations": self.num_evaluations,
                            "strategy_win_rate": avg_pnl_per_1000_rounds,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        f.write(json.dumps(results_json)+"\n")
                write_global_results()

                def write_results_for_game(output_dir: Path, game: IndianPokerGame):
                    avg_pnl_per_1000_rounds = {}
                    sorted_three_tuple = tuple(sorted(game.strategies.keys()))
                    for strategy in game.strategies.keys():
                        avg_pnl_per_1000_rounds[strategy] = (self.pnl_for_three_tuple[sorted_three_tuple][strategy]) * 1000 / (self.number_of_rounds_for_three_tuple[sorted_three_tuple][strategy] if self.number_of_rounds_for_three_tuple[sorted_three_tuple][strategy] > 0 else 1)
                    self.logger.info(f"Average pnl per 1000 games for {sorted_three_tuple}: {avg_pnl_per_1000_rounds}")
                    with open(f'{output_dir}/results.txt', 'a') as f:
                        results_json = {
                            "num_evaluations": self.num_evaluations,
                            "strategy_win_rate": avg_pnl_per_1000_rounds,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        f.write(json.dumps(results_json)+"\n")

                def generate_picture_for_game(output_dir: Path, game: IndianPokerGame):
                    num_rounds_used = len( game.historical_stack_sizes )
                    size_by_player = {}
                    for s in game.historical_stack_sizes:
                        for k,v in s.items():
                            if k not in size_by_player:
                                size_by_player[k] = []
                            size_by_player[k].append(v)
                    for k,v in size_by_player.items():
                        plt.plot( list(range(num_rounds_used)), v, label=k )
                    plt.legend()
                    plt.title(f'Evaluation #{self.num_evaluations}')
                    plt.savefig(f'{output_dir}/results{self.num_evaluations % 10}.png')
                    plt.clf()
                
                for strategies, game in self.last_game.items():
                    # make the directory if needed
                    formatted_sorted_strategy_tuple = ",".join(strategies)
                    output_dir = RESULTS_DIR / formatted_sorted_strategy_tuple
                    if not output_dir.exists():
                        output_dir.mkdir()
                    generate_picture_for_game(output_dir, game)
                    write_results_for_game(output_dir, game)

                self.num_evaluations += 1
                last_write_time = datetime.datetime.now()
        finally:
            self.is_running = False

if __name__ == "__main__":
    evaluator = ThreePlayerEvaluator()
    evaluator.load_strategies()
    strategies = evaluator.start_evaluating_strategies()
