# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Indian Poker game engine and strategy evaluator. Players are dealt a single card they cannot see (but can see opponents' cards), then bet in rounds. The system evaluates strategies by running 3-player round-robin tournaments.

## Commands

```bash
# Run Flask web app (local)
source venv/bin/activate
flask --app app run

# Run with Docker
docker compose up

# Run game engine standalone
python indianpoker.py

# Run evaluator standalone
python evaluator.py
```

Environment variables: `PORT`, `APP_TITLE`, `APP_DESCRIPTION`, `VERBOSE` (enables debug logging). See `.env.example`.

## Architecture

- **`indianpoker.py`** — Core game engine. Defines `Action`, `PlayerInformation`, `RoundState`, `Strategy` (base class), `IndianPokerGame`, and `simulate_game()`. Strategies receive a frozen `RoundState` with their own card hidden (`card=-1`). Invalid actions auto-fold.
- **`evaluator.py`** — `ThreePlayerEvaluator` runs all 3-player combinations of loaded strategies in a background thread, continuously simulating 1000-round games and writing results (PnL per 1000 rounds) + matplotlib charts to `results/`.
- **`app.py`** — Flask web UI for uploading strategies, viewing results, and browsing interesting game logs. Strategies are hot-reloaded on upload via `evaluator.restart()`.
- **`strategies/`** — Active strategy files loaded by the evaluator. Each file must export a module-level `strategy` variable set to the Strategy class (not an instance).
- **`example_strategies/`** — Reference implementations (e.g., `RandomStrategy.py`).
- **`my_strategies/`** — Personal strategy development area (not loaded by evaluator).

## Writing a Strategy

A strategy file must:
1. Import from `indianpoker`: `Action`, `RoundState`, `Strategy`
2. Subclass `Strategy` with a unique `player_id` class attribute
3. Implement `make_decision(self, state: RoundState) -> Action`
4. Export: `strategy = MyStrategyClass` (the class itself, not an instance)

Key `RoundState` helpers: `get_delta_to_call_for_player()`, `get_minimum_raise_delta_for_player()`, `can_check_currently()`, `check_call()`, `check_fold()`, `get_all_in_action_for_player_id()`.

Cards are floats 1.0–13.75 (0.25 increments represent suits). Higher card wins at showdown.
