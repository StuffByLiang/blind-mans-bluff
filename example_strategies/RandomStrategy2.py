import random
from indianpoker import Action, RoundState, Strategy

class RandomStrategy(Strategy):
    player_id = "RandomStrategy2"

    def make_decision(self, state: RoundState) -> Action:
        # Simple strategy: do a random action
        valid_actions = ['fold', 'call', 'raise', 'check']
        
        action = random.choice(valid_actions)

        if action == 'fold':
            return Action('fold')
        elif action == 'call':
            return Action('call', amount=state.get_amount_to_call_for_player(self.player_id))
        elif action == 'raise':
            return Action('raise', amount=state.get_minimum_raise_amount_for_player(self.player_id))
        elif action == 'check':
            return Action('check')

strategy = RandomStrategy