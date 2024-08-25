# import all strategies from strategies folder and play mulitple rounds of indian poker
from indianpoker import Strategy, IndianPokerGame, simulate_game
from threading import Lock
import os
import logging
import datetime
import matplotlib.pyplot as plt

class Evaluator:
    def __init__(self, logger = logging.getLogger(__name__)):
        self.logger = logger
        self.strategies = {}
        self.strategy_average_stack_size = {}
        self.lock = Lock()

    def load_strategies(self):
        strategies = {}
        for file in os.listdir('strategies'):
            if file.endswith('.py') and file != 'indianpoker.py':
                try:
                    strategy_module = __import__(f'strategies.{file[:-3]}', fromlist=[''])
                    strategy_class: Strategy = getattr(strategy_module, "strategy")
                    strategies[strategy_class.player_id] = strategy_class()
                except Exception as e:
                    self.logger.exception(f"Error loading strategy from file {file}")
        return strategies
    
    def reload_strategies(self):
        with self.lock:
            # pitch the strategies against each other 
            self.strategies = self.load_strategies()
            self.logger.info(f"Reloaded Strategies: strategies playing: {self.strategies}")

            self.strategy_average_stack_size = {
                strategy: 200 for strategy in self.strategies
            }

    
    def evaluate_strategies(self):
        number_of_games = 0
        ante=5
        starting_stack=200
        rounds=100

        last_write_time = datetime.datetime.now()

        log_every = 1000

        while True:
            with self.lock:
                if len(self.strategies) < 2:
                    continue
                game = simulate_game(self.strategies, ante, starting_stack, rounds)

                for strategy in self.strategies:
                    number_of_games += 1
                    self.strategy_average_stack_size[strategy] = (self.strategy_average_stack_size[strategy] * (number_of_games - 1) + game.stack_sizes[strategy]) / number_of_games

                if number_of_games % log_every == 0: 
                    self.logger.info(f"Final Stack Sizes: {game.stack_sizes}")
                    self.logger.info(f"Average Stack Sizes: {self.strategy_average_stack_size}")
                if datetime.datetime.now() - last_write_time > datetime.timedelta(seconds=10):
                    with open('results/results.txt', 'w+') as f:
                        results_json = {
                            "number_of_games": number_of_games,
                            "strategy_average_stack_size": self.strategy_average_stack_size,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        f.write(str(results_json))
                    num_rounds_used = len( game.historical_stack_sizes )
                    size_by_player = {}
                    for s in game.historical_stack_sizes:
                        for k,v in s.items():
                            if k not in size_by_player:
                                size_by_player[k] = []
                            size_by_player[k].append(v)
                    for k,v in size_by_player.items():
                        plt.plot( list(range(num_rounds_used)), v, label=k )
                    plot.legend()
                    plt.savefig('results/results.png')
                    plt.clf()
                    last_write_time = datetime.datetime.now()

if __name__ == "__main__":
    evaluator = Evaluator()
    evaluator.reload_strategies()
    strategies = evaluator.evaluate_strategies()
