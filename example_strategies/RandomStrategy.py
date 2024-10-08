import random
from indianpoker import Action, RoundState, Strategy

class RandomStrategy(Strategy):
    player_id = "RandomStrategy"

    def make_decision(self, state: RoundState) -> Action:
        # Simple strategy: do a random action
        valid_actions = ['fold', 'call', 'raise', 'check']
        
        action = random.choice(valid_actions)

        if action == 'fold':
            return Action('fold')
        elif action == 'call':
            return Action('call', delta=state.get_delta_to_call_for_player(self.player_id))
        elif action == 'raise':
            return Action('raise', delta=state.get_minimum_raise_delta_for_player(self.player_id))
        elif action == 'check':
            return Action('check')

strategy = RandomStrategy