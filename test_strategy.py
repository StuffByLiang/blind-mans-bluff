"""
Quick evaluation harness for developing strategies.
Usage: python test_strategy.py strategies.MyNewStrategy [games] [rounds_per_game]

Runs the target strategy in all 3-player combos against loaded strategies
and prints PnL per 1000 rounds.
"""
import sys
import importlib
import itertools
import logging
from collections import defaultdict
from indianpoker import simulate_game

OPPONENT_MODULES = [
    "strategies.AlphaShitter",
    "strategies.Chirpy2",
    "strategies.Chirpy3",
    "strategies.Opener",
]

def load_strategy(module_path: str):
    mod = importlib.import_module(module_path)
    importlib.reload(mod)
    return mod.strategy  # returns the class

def run(target_module: str, num_games: int = 30, rounds_per_game: int = 1000):
    target_cls = load_strategy(target_module)

    # Load opponents, skip if same player_id as target
    opp_classes = []
    for mod_path in OPPONENT_MODULES:
        try:
            cls = load_strategy(mod_path)
            if cls.player_id != target_cls.player_id:
                opp_classes.append(cls)
        except Exception as e:
            print(f"Warning: could not load {mod_path}: {e}")

    pnl = defaultdict(int)
    total_rounds = defaultdict(int)
    combo_results = {}

    # Run target against every pair of opponents
    for pair in itertools.combinations(opp_classes, 2):
        combo_pnl = defaultdict(int)
        combo_rounds = defaultdict(int)

        for _ in range(num_games):
            strats = {cls.player_id: cls() for cls in [target_cls, *pair]}
            game = simulate_game(strats, ante=5, starting_stack=200, rounds=rounds_per_game)

            for sid, stack in game.stack_sizes.items():
                r = game.turn_busted.get(sid, len(game.round_history))
                pnl[sid] += stack - 200
                total_rounds[sid] += r
                combo_pnl[sid] += stack - 200
                combo_rounds[sid] += r

        combo_key = tuple(sorted(cls.player_id for cls in pair))
        combo_results[combo_key] = (combo_pnl, combo_rounds)

    # Print per-combo breakdown
    target_id = target_cls.player_id
    print(f"\n{'='*60}")
    print(f"Target: {target_id}  |  {num_games} games x {rounds_per_game} rounds each")
    print(f"{'='*60}")

    for combo_key, (cpnl, crounds) in sorted(combo_results.items()):
        print(f"\nvs {combo_key[0]}, {combo_key[1]}:")
        for sid in sorted(cpnl, key=lambda s: cpnl[s], reverse=True):
            rate = cpnl[sid] * 1000 / max(crounds[sid], 1)
            marker = " ***" if sid == target_id else ""
            print(f"  {sid:<20} {rate:>+10.1f} PnL/1k rounds{marker}")

    # Print global summary
    print(f"\n{'─'*60}")
    print(f"{'GLOBAL SUMMARY':^60}")
    print(f"{'─'*60}")
    print(f"{'Strategy':<20} {'PnL/1k rounds':>15} {'Total Rounds':>15}")
    for sid in sorted(pnl, key=lambda s: pnl[s], reverse=True):
        rate = pnl[sid] * 1000 / max(total_rounds[sid], 1)
        marker = " ***" if sid == target_id else ""
        print(f"{sid:<20} {rate:>+15.1f} {total_rounds[sid]:>15}{marker}")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)  # silence game logs
    target = sys.argv[1] if len(sys.argv) > 1 else "strategies.AlphaShitter"
    games = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    run(target, games, rounds)
