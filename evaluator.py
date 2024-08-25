# import all strategies from strategies folder and play mulitple rounds of indian poker
from indianpoker import Strategy, IndianPokerGame, simulate_game
from importlib import reload
from pathlib import Path
from threading import Lock
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
        self.request_stop = False
        self.stopped = False

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
                    reload(strategy_module)
                    strategy_class: Strategy = getattr(strategy_module, "strategy")
                    self.strategies[strategy_class.player_id] = strategy_class()
                    self.logger.info(f"Loaded strategy {strategy_class.player_id} from file {file})")
                except Exception as e:
                    self.logger.exception(f"Error loading strategy from file {file}")
        
        # pitch the strategies against each other
        self.logger.info(f"Reloaded Strategies: strategies playing: {self.strategies}")

        self.number_of_chips = {
            strategy: 0 for strategy in self.strategies
        }
        self.number_of_games = {
            strategy: 0 for strategy in self.strategies
        }
    
    def stop(self):
        self.request_stop = True
        while not self.stopped:
            print("waiting for evaluator to stop")
            pass

    def evaluate_strategies(self):
        ante=5
        starting_stack=200
        rounds=1000

        last_write_time = datetime.datetime.now()

        last_log_game = 0
        log_every = 1000
        last_write_num = 0

        self.stopped = True

        while True:
            if len(self.strategies) < 3:
                continue
            for strategies in itertools.combinations(self.strategies, 3):
                if self.request_stop:
                    self.request_stop = False
                    self.stopped = True
                    return
                game = simulate_game({k: v for k, v in self.strategies.items() if k in strategies}, ante, starting_stack, rounds)

                for strategy in strategies:
                    self.number_of_games[strategy] += len( game.historical_stack_sizes )
                    self.number_of_chips[strategy] += game.stack_sizes[strategy] - starting_stack

            avg_win_rate = {}
            for strategy in self.strategies:
                avg_win_rate[strategy] = (self.number_of_chips[strategy]) * 1000 / self.number_of_games[strategy]

            # num games is same for each strategy so can just take the first one
            number_of_games = list(self.number_of_games.values())[0]

            if number_of_games > last_log_game + log_every:
                last_log_game += log_every
                self.logger.info(f"Average Win Rate: {avg_win_rate}")

            if datetime.datetime.now() - last_write_time > datetime.timedelta(seconds=1):
                with open('results/results.txt', 'a') as f:
                    results_json = {
                        "number_of_games": number_of_games,
                        "strategy_win_rate": avg_win_rate,
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
    evaluator.reload_strategies()
    strategies = evaluator.evaluate_strategies()
