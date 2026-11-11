import logging
import unittest

from indianpoker import Action, IndianPokerGame, Strategy


class ScriptedStrategy(Strategy):
    def __init__(self, player_id, decisions):
        self.player_id = player_id
        self.decisions = iter(decisions)

    def make_decision(self, state):
        decision = next(self.decisions)
        return decision(state) if callable(decision) else decision


def check_call(player_id):
    return lambda state: state.check_call(player_id)


class BettingTurnTests(unittest.TestCase):
    def play_round(self, decisions):
        strategies = {
            player_id: ScriptedStrategy(player_id, actions)
            for player_id, actions in decisions.items()
        }
        logger = logging.Logger("betting_turn_tests", level=logging.CRITICAL)
        game = IndianPokerGame(strategies, ante=5, starting_stack=200, logger=logger)
        game.non_busted_player_id_order = list(strategies)
        game.next_ante_player_id = list(strategies)[-1]
        game.make_shuffled_deck = lambda: [1, 8, 13][-len(strategies):]
        state = game.play_round()
        self.assertEqual(sum(game.stack_sizes.values()), 200 * len(strategies))
        return game, state

    def assert_actions(self, state, expected):
        self.assertEqual(
            [(a.player_id, a.action_type, a.delta) for a in state.betting_history],
            expected,
        )

    def test_heads_up_all_in_allows_opponent_to_call(self):
        game, state = self.play_round({
            "A": [Action("raise", delta=200)],
            "B": [check_call("B")],
        })
        self.assert_actions(state, [("A", "raise", 200), ("B", "call", 195)])
        self.assertEqual(game.stack_sizes, {"A": 400, "B": 0})

    def test_heads_up_all_in_allows_opponent_to_fold(self):
        game, state = self.play_round({
            "A": [Action("raise", delta=200)],
            "B": [Action("fold")],
        })
        self.assert_actions(state, [("A", "raise", 200), ("B", "fold", 0)])
        self.assertEqual(game.stack_sizes, {"A": 205, "B": 195})

    def test_three_player_all_in_allows_both_opponents_to_respond(self):
        for b_folds in (False, True):
            for c_folds in (False, True):
                with self.subTest(b_folds=b_folds, c_folds=c_folds):
                    _, state = self.play_round({
                        "A": [Action("raise", delta=200)],
                        "B": [Action("fold") if b_folds else check_call("B")],
                        "C": [Action("fold") if c_folds else check_call("C")],
                    })
                    self.assert_actions(state, [
                        ("A", "raise", 200),
                        ("B", "fold", 0) if b_folds else ("B", "call", 200),
                        ("C", "fold", 0) if c_folds else ("C", "call", 195),
                    ])

    def test_all_in_reraise_returns_action_to_original_raiser(self):
        game, state = self.play_round({
            "A": [Action("raise", delta=100), check_call("A")],
            "B": [Action("raise", delta=200)],
            "C": [check_call("C")],
        })
        self.assert_actions(state, [
            ("A", "raise", 100),
            ("B", "raise", 200),
            ("C", "call", 195),
            ("A", "call", 100),
        ])
        self.assertEqual(game.stack_sizes, {"A": 600, "B": 0, "C": 0})

    def test_all_in_after_checks_returns_action_to_both_players(self):
        _, state = self.play_round({
            "A": [Action("check"), check_call("A")],
            "B": [Action("check"), check_call("B")],
            "C": [Action("raise", delta=195)],
        })
        self.assert_actions(state, [
            ("A", "check", 0),
            ("B", "check", 0),
            ("C", "raise", 195),
            ("A", "call", 195),
            ("B", "call", 195),
        ])

    def test_non_all_in_reraise_does_not_ask_raiser_to_act_again(self):
        _, state = self.play_round({
            "A": [Action("raise", delta=10), check_call("A")],
            "B": [Action("raise", delta=20)],
            "C": [check_call("C")],
        })
        self.assert_actions(state, [
            ("A", "raise", 10),
            ("B", "raise", 20),
            ("C", "call", 20),
            ("A", "call", 10),
        ])

    def test_non_all_in_raise_ends_after_call_and_fold(self):
        _, state = self.play_round({
            "A": [Action("raise", delta=10)],
            "B": [check_call("B")],
            "C": [Action("fold")],
        })
        self.assert_actions(state, [
            ("A", "raise", 10),
            ("B", "call", 10),
            ("C", "fold", 0),
        ])

    def test_check_only_round_ends_after_each_player_acts_once(self):
        _, state = self.play_round({
            "A": [Action("check")],
            "B": [Action("check")],
            "C": [Action("check")],
        })
        self.assert_actions(state, [
            ("A", "check", 0),
            ("B", "check", 0),
            ("C", "check", 0),
        ])


if __name__ == "__main__":
    unittest.main()
