from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from itertools import cycle
import random
import logging

#logger = logging.getLogger(__name__)
class f:
    def debug(self,s):
        print(s)
logger=f()


class Action:
    def __init__(self, action_type: str, player_id: str = "", delta: int = 0):
        """
        Represents an action in the game.

        Parameters:
        - action_type: A string that can be 'fold', 'call', 'raise', 'check'
        - player_id: The ID of the player performing the action.
        - delta: The incremental amount that the player has put into the pot at that point for 'call' or 'raise'.

        Note: if the action is 'fold' or 'check', the amount is ignored.

        Note: an all in is a raise with the remaining stack size of the player, or a call if the stack size is less than the current bet.
              see get_all_in_action_for_player_id in RoundState for more details.
        """
        self.action_type = action_type
        self.player_id = player_id
        if action_type == 'fold' or action_type == 'check':
            self.delta = 0
        else:
            self.delta = delta

    def __repr__(self):
        return f"Action(type={self.action_type}, player_id={self.player_id}, delta={self.delta})"

@dataclass
class PlayerInformation:
    """
    PlayerInformation class to store the information of a player.

    Attributes:
    - player_id: The ID of the player.
    - order: The order of the player, 0 indexed.
    - card: The card that the player has. -1 if the card is hidden.
    - stack_size: The remaining stack size of the player.
    - has_folded: A boolean indicating whether the player has folded.
    """
    player_id: str
    order: int
    card: float
    remaining_stack_size: int
    has_folded: bool = False

class RoundState:
    """
    RoundState class to store the state of the round.

    Attributes:
    - pot: The current pot size.
    - current_bet_total: The current total bet amount.
    - betting_history: A sorted list of Action taken by the players representing the betting history.
    - player_information: A sorted dict of player_id -> PlayerInformation in the order of the players.
                          The first player in this list is the starting player.
    """
    pot: int = 0
    current_bet_total: int = 0
    last_raise_delta: int = 0
    betting_history: list[Action] = []
    player_information: OrderedDict[str, PlayerInformation] = []

    def __init__(self, pot: int, player_information: OrderedDict[str, PlayerInformation]):
        self.pot = pot
        self.current_bet_total = 0
        self.last_raise_delta = 0
        self.betting_history = []
        self.player_information = player_information

    def get_state_hiding_card_for_player_id(self, player_id: str):
        """
        Returns a new RoundState object with the player_id's card hidden from their PlayerInformation
        """
        new_state = deepcopy(self)
        new_state.player_information[player_id].card = -1
        return new_state

    def get_money_put_in_by_player(self, player_id: str) -> int:
        """
        Returns the total amount of money put in by the player in the current round.
        """
        return sum(action.delta for action in self.betting_history if action.player_id == player_id)

    def is_player_all_in(self, player_id: str) -> bool:
        """
        Returns True if the player is all-in in the current round (and therefore cannot do any actions).
        """
        return self.player_information[player_id].remaining_stack_size == 0

    def is_round_finished(self) -> bool:
        """
        Returns True if the round is finished:
        - All players have folded except one.
        - All players have called the current raiser.
        - All players have checked.

        This will be false if the round is still ongoing and passed as a parameter to the make_decision method of the Strategy class.
        """
        # if the first couple n-1 actions are all folds, then the round is finished
        if len(self.betting_history) == len(self.player_information) - 1:
            count = 0
            for action in self.betting_history:
                if action.action_type == 'fold':
                    count += 1
            if count == len(self.betting_history):
                return True

        def ok(player: PlayerInformation):
            return any([
                player.has_folded,
                player.remaining_stack_size == 0,
                self.get_money_put_in_by_player(player.player_id) == self.current_bet_total,
            ])
        return (
            len(self.betting_history) >= len(self.player_information)
            and all(ok(player) for player in self.player_information.values())
          )

    def can_check_currently(self, player_id) -> bool:
        """
        Returns True if the player can check currently.
        """
        return self.get_money_put_in_by_player(player_id) == self.current_bet_total

    def get_delta_to_call_for_player(self, player_id: str) -> int:
        """
        Returns the delta that the player needs to make a valid call.

        This is either the difference between the current bet and the money put in by the player, or the player's remaining stack size.
        """
        return min(self.player_information[player_id].remaining_stack_size, self.current_bet_total - self.get_money_put_in_by_player(player_id))

    def get_all_in_action_for_player_id(self, player_id: str) -> Action:
        """
        Returns an Action object representing the player going all-in. This is a special case

        if the player's stack size >= the current bet, it is a raise

        if the player's stack size < the current bet, it considered a "call" with a smaller amount
        """
        if self.player_information[player_id].remaining_stack_size > self.current_bet_total:
            return Action('raise', player_id=player_id, delta=self.player_information[player_id].remaining_stack_size)
        else:
            return Action('call', player_id=player_id, delta=self.player_information[player_id].remaining_stack_size)

    def get_minimum_raise_delta_for_player(self, player_id: str) -> int:
        """
        Returns the minimum delta that the player can raise.

        You must raise at minimum the last raise delta, or 1, UNLESS it is an all in, in which case there are no minimum limitations to a raise.

        This needs to be in addition to the delta the player needs to call.
        """
        call_delta = self.get_delta_to_call_for_player(player_id)
        raise_delta = max(min(self.last_raise_delta + call_delta, self.player_information[player_id].remaining_stack_size), 1)
        return raise_delta

    def __repr__(self):
        return f"RoundState(pot={self.pot}, current_bet_total={self.current_bet_total}, last_raise_delta={self.last_raise_delta}, betting_history={self.betting_history}, player_information={self.player_information})"

    # helpers
    def check_fold(self, player_id):
        return Action("check") if self.can_check_currently(player_id) else Action("fold")

    def check_call(self, player_id):
      if self.can_check_currently(player_id):
        return Action("check")
      else:
        return Action("call", delta=self.get_delta_to_call_for_player(player_id))


class Strategy:
    player_id = "" # The player ID for the strategy. You must override this.

    def make_decision(self, state: RoundState) -> Action:
        """
        Makes a decision based on the initial stack sizes, betting history, opponent cards, and the starting pot.

        Any invalid Action will result in a fold, thus it is recommended to check call amounts and minimum raise amounts using
        state.get_delta_to_call_for_player(player_id) and state.get_minimum_raise_delta_for_player(player_id) respectively.

        Returns:
        An Action object representing the decision. It's optional to set the player_id in the Action object
        """
        pass

    def start_new_round(self) -> None:
        """
        Called at the start of a new round.
        """
        pass

class IndianPokerGame:
    def __init__(self, strategies: dict[str, Strategy], ante: int, starting_stack: int):
        """
        Initialize the game with the given strategies, ante, and starting stack sizes.

        Parameters:
        - strategies: A dict of player_id -> Strategy objects representing the players in the game.
        - ante: The ante amount that a player has to pay at the start of each round.
        - starting_stack: The starting stack size for each player.

        Attributes:
        - stack_sizes: A dict of player_id -> stack_size representing the remaining stack size of each player.
        - player_id_order: A list of player IDs representing the order of the players.
        - first_player_idx: The index of the first player in the player_id_order list.
        - buster_players: A set of player IDs who have busted (stack size == 0).
        """
        self.strategies = strategies
        self.ante = ante

        self.stack_sizes = {strategy.player_id: starting_stack for strategy in strategies.values()}
        self.historical_stack_sizes = [ deepcopy( self.stack_sizes ) ]
        self.player_id_order = [strategy.player_id for strategy in strategies.values()]
        self.first_player_idx = 0
        self.busted_players = set()
        random.shuffle(self.player_id_order)

    def make_shuffled_deck(self) -> list[int]:
        """
        Creates a deck of cards with numbers from 1 to 13 incrementing by 0.25 to simulate suits.

        effectively,
            1 = 2 of diamonds
            1.25 = 2 of clubs
            1.5 = 2 of hearts
            1.75 = 2 of spades

            10 = Jack
            11 = Queen
            12 = King
            13 = Ace
        """
        deck = [i + 0.25 * j for i in range(1, 14) for j in range(4)]
        random.shuffle(deck)
        return deck

    def get_initial_round_state(self) -> RoundState:
        # pretty much deals the cards
        pot = 0
        deck = self.make_shuffled_deck()
        player_information = OrderedDict()

        # Determine the starting index based on first_player_idx
        num_players = len(self.player_id_order)
        player_cycle = cycle(self.player_id_order)

        # Skip players until reaching the starting player
        for _ in range(self.first_player_idx):
            next(player_cycle)

        # Skip players until reaching the first player that has not busted
        player_id = next(player_cycle)
        while player_id in self.busted_players:
            player_id = next(player_cycle)

        # first player pays the entire ante or whatever is left in their stack
        ante_amount = min(self.stack_sizes[player_id], self.ante)
        self.stack_sizes[player_id] -= ante_amount
        pot += ante_amount

        # the player after the ante payer gets the first card
        for idx in range(num_players):
            player_id = next(player_cycle)
            if player_id not in self.busted_players: # Skip busted players
                player_information[player_id] = PlayerInformation(
                    player_id=player_id,
                    order=idx,
                    card=deck.pop(),
                    remaining_stack_size=self.stack_sizes[player_id]
                )

        # update first player index for the next round
        self.first_player_idx = (self.first_player_idx + 1) % num_players

        return RoundState(pot=pot, player_information=player_information)

    def play_round(self):
        """
        Play starts with the first player and goes in order

        The round ends when
        - all players have folded except one
        - all players have called the current raiser
        - all players have checked
        """
        # Initial round setup
        round_state = self.get_initial_round_state()
        player_id_cycle = cycle(round_state.player_information.keys())
        num_players = len( round_state.player_information )
        # debug log each player's card
        for player_info in round_state.player_information.values():
            logger.debug(f"{player_info.player_id} received card: {player_info.card}")

        # Perform betting rounds
        last_bet = False
        player_id = next(player_id_cycle)
        while True:
            num_folds = sum( 1 for p in round_state.player_information.values() if p.has_folded )
            need_action = num_players - num_folds - (1 if last_bet else 0)
            made_move = 0
            for rep in range( need_action ):
                # HACK: if everyone folds, you win
                if sum( 1 for p in round_state.player_information.values() if p.has_folded ) == num_players - 1:
                    made_move = need_action
                    invalid_action = False
                    break
                # Get decision from the player's strategy
                while (player_info := round_state.player_information[player_id]).has_folded:
                    logger.debug(f"skipping {player_id} because they have has folded")
                    player_id = next( player_id_cycle )
                    
                logger.debug(f"--- Action on {player_id} ---")
                action = None
                try:
                    strategy = self.strategies[player_id]
                    action = strategy.make_decision(round_state.get_state_hiding_card_for_player_id(player_id))
                    action.player_id = player_id
                except Exception as e:
                    logger.exception(f"Error getting decision for {player_id}, folding.")
                    action = Action('fold', player_id=player_id)
                
                # Process action
                invalid_action = False
                if action.action_type == 'fold':
                    logger.debug(f"{player_id} folds.")
                    player_info.has_folded = True

                elif action.action_type == 'call':
                    call_delta = action.delta
                    if call_delta == 0:
                        logger.debug(f"{player_id} folds due to a call amount of 0")
                        invalid_action = True
                    elif call_delta != round_state.get_delta_to_call_for_player(player_id):
                        logger.debug(f"{player_id} folds due to invalid call amount.")
                        invalid_action = True
                    elif call_delta > round_state.player_information[player_id].remaining_stack_size:
                        logger.debug(f"{player_id} folds due to stack size too small.")
                        invalid_action = True
                    else:
                        round_state.player_information[player_id].remaining_stack_size -= call_delta
                        round_state.pot += call_delta
                        logger.debug(f"{player_id} calls {call_delta}.")

                elif action.action_type == 'raise':
                    call_and_raise_delta = action.delta # this includes the amount needed to call as well
                    if call_and_raise_delta < round_state.get_minimum_raise_delta_for_player(player_id):
                        logger.debug(f"{player_id} folds due to invalid raise amount.")
                        invalid_action = True
                    elif call_and_raise_delta > round_state.player_information[player_id].remaining_stack_size:
                        logger.debug(f"{player_id} folds due to stack size too small.")
                        invalid_action = True
                    else:
                        player_current_bet = round_state.get_money_put_in_by_player(player_id)
                        call_delta = round_state.get_delta_to_call_for_player(player_id) # this is the amount needed to call
                        raise_delta = call_and_raise_delta - call_delta # this is the amount raised

                        round_state.pot += call_and_raise_delta
                        round_state.last_raise_delta = raise_delta
                        round_state.current_bet_total = player_current_bet + call_delta + raise_delta
                        round_state.player_information[player_id].remaining_stack_size -= call_and_raise_delta

                        logger.debug(f"{player_id} raises {raise_delta} (call {call_delta}) to the pot for a total bet of {round_state.current_bet_total}.")

                elif action.action_type == 'check':
                    if not round_state.can_check_currently(player_id):
                        logger.debug(f"{player_id} folds due to invalid check.")
                        invalid_action = True
                    else:
                        logger.debug(f"{player_id} checks.")

                else:
                    logger.debug(f"{player_id} folds due to invalid action type.")
                    invalid_action = True

                player_id = next( player_id_cycle )
                # Record the action
                if not invalid_action:
                    round_state.betting_history.append(action)
                    if action.action_type != 'raise':
                        made_move += 1
                    else:
                        last_bet = True
                        break
                else:
                    player_info.has_folded = True
                    round_state.betting_history.append(Action('fold'))
                    made_move += 1
                
            if made_move == need_action:
                break

        # Determine the winner and update stacks
        # TODO: Implement side pot logic, winner can only win up to the amount they put in from each player
        remaining_players = [pid for pid in round_state.player_information if not round_state.player_information[pid].has_folded]
        winner = None
        if len(remaining_players) == 1:
            winner = remaining_players[0]
            logger.debug(f"{winner} wins the pot of {round_state.pot} by default.")
        else:
            # Compare cards to find the winner
            winner = max(remaining_players, key=lambda pid: round_state.player_information[pid].card)
            logger.debug(f"{winner} wins the pot of {round_state.pot} with a higher card.")

        # Update stack_sizes of each player
        for pid in round_state.player_information:
            if pid == winner:
                self.stack_sizes[pid] = round_state.player_information[pid].remaining_stack_size + round_state.pot
            else:
                self.stack_sizes[pid] = round_state.player_information[pid].remaining_stack_size
        logger.debug(f"Stack Sizes: {self.stack_sizes}")
        if sum(self.stack_sizes.values()) != 600:
            logger.debug(f"ERROR: Stack sizes not equal to 600: {self.stack_sizes}")

        self.historical_stack_sizes.append( deepcopy( self.stack_sizes ) )

        # update busted players
        for pid in self.stack_sizes:
            if self.stack_sizes[pid] == 0:
                self.busted_players.add(pid)

    def has_at_least_2_players_left(self):
        return len(self.stack_sizes) - len(self.busted_players) >= 2

def simulate_game(strategies: dict[str, Strategy], ante: int, starting_stack: int, rounds: int) -> IndianPokerGame:
    game = IndianPokerGame(strategies, ante, starting_stack)
    for round_number in range(1, rounds + 1):
        logger.debug(f"\n--- Round {round_number} ---")
        game.play_round()
        if not game.has_at_least_2_players_left():
            logger.debug("Game over! Less than 2 players remaining.")
            break
    logger.debug(f"\nFinal Stack Sizes: {game.stack_sizes}")
    return game

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    class RandomStrategy(Strategy):
        def __init__(self, player_id: str):
            self.player_id = player_id

        def make_decision(self, game_state: RoundState) -> Action:
            # Simple strategy: do a random action
            valid_actions = ['fold', 'call', 'raise', 'check']

            action = random.choice(valid_actions)

            if action == 'fold':
                return Action('fold')
            elif action == 'call':
                return Action('call', delta=game_state.get_delta_to_call_for_player(self.player_id))
            elif action == 'raise':
                return Action('raise', delta=game_state.get_minimum_raise_delta_for_player(self.player_id))
            elif action == 'check':
                return Action('check')

    strategies = {
        'Player 1': RandomStrategy('Player 1'),
        'Player 2': RandomStrategy('Player 2'),
        'Player 3': RandomStrategy('Player 3'),
    }

    simulate_game(strategies, ante=5, starting_stack=200, rounds=20)
