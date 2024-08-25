# import all strategies from strategies folder and play mulitple rounds of indian poker
from indianpoker import Strategy, IndianPokerGame, simulate_game
from threading import Lock
from pathlib import Path
import os
import logging
import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('agg')
import itertools

RESULTS_DIR = Path('results')

class Evaluator:
    def __init__(self, logger = logging.getLogger(__name__)):
        self.logger = logger
        self.strategies = {}
        self.number_of_chips = {}
        self.number_of_games = {}
        self.lock = Lock()
        self.stop = False

        # remove all files from results folder and make it if needed
        if not RESULTS_DIR.exists():
            RESULTS_DIR.mkdir()
            for file in RESULTS_DIR.iterdir():
                file.unlink()

    def load_strategies(self):
        self.strategies = {}
        for file in os.listdir('strategies'):
            if file.endswith('.py') and file != 'indianpoker.py':
                try:
                    strategy_module = __import__(f'strategies.{file[:-3]}', fromlist=[''])
                    strategy_class: Strategy = getattr(strategy_module, "strategy")
                    self.strategies[strategy_class.player_id] = strategy_class()
                    self.logger.info(f"Loaded strategy {strategy_class.player_id} from file {file})")
                except Exception as e:
                    self.logger.exception(f"Error loading strategy from file {file}")

        self.number_of_chips = {
            strategy: 0 for strategy in self.strategies
        }
        self.number_of_games = {
            strategy: 0 for strategy in self.strategies
        }
        self.logger.info(f"Reloaded Strategies: strategies playing: {self.strategies}")

    def evaluate_strategies(self):
        ante=5
        starting_stack=200
        rounds=100

        last_write_time = datetime.datetime.now()

        last_log_game = 0
        log_every = 100
        last_write_num = 0

        while True:
            with self.lock:
                if len(self.strategies) < 3:
                    continue
                for strategies in itertools.combinations(self.strategies, 3):
                    if self.stop:
                        return
                    game = simulate_game({k: v for k, v in self.strategies.items() if k in strategies}, ante, starting_stack, rounds)

                    for strategy in strategies:
                        self.number_of_games[strategy] += 1
                        self.number_of_chips[strategy] += game.stack_sizes[strategy]

                avg_stack_size = {}
                for strategy in self.strategies:
                    avg_stack_size[strategy] = self.number_of_chips[strategy] / self.number_of_games[strategy]

                # num games is same for each strategy so can just take the first one
                number_of_games = list(self.number_of_games.values())[0]

                if number_of_games > last_log_game + log_every:
                    last_log_game += log_every
                    self.logger.info(f"Average Stack Sizes: {avg_stack_size}")

                if datetime.datetime.now() - last_write_time > datetime.timedelta(seconds=1):
                    with open('results/results.txt', 'a') as f:
                        results_json = {
                            "number_of_games": number_of_games,
                            "strategy_average_stack_size": avg_stack_size,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        f.write(str(results_json)+"\n")
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
                    plt.savefig(f'results/results{last_write_num % 10}.png')
                    plt.clf()
                    last_write_num += 1
                    last_write_time = datetime.datetime.now()

if __name__ == "__main__":
    evaluator = Evaluator()
    evaluator.load_strategies()
    evaluator.evaluate_strategies()
