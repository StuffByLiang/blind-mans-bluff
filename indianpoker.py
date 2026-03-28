from collections import OrderedDict
from dataclasses import dataclass, replace
from io import StringIO
from itertools import cycle
from types import MappingProxyType
import random
import logging

@dataclass(frozen=True)
class Action:
    """
    Represents an action in the game.

    Attributes:
    - action_type: A string that can be 'fold', 'call', 'raise', 'check'
    - player_id: The ID of the player performing the action.
    - delta: The incremental amount that the player has put into the pot at that point for 'call' or 'raise'.

    Note: if the action is 'fold' or 'check', the amount is ignored.

    Note: an all in is a raise with the remaining stack size of the player, or a call if the stack size is less than the current bet.
          see get_all_in_action_for_player_id in RoundState for more details.
    """
    action_type: str
    player_id: str = ""
    delta: int = 0

    def __post_init__(self):
        if self.action_type in ('fold', 'check'):
            object.__setattr__(self, 'delta', 0)

    def __repr__(self):
        return f"Action(type={self.action_type}, player_id={self.player_id}, delta={self.delta})"

@dataclass(frozen=True)
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

    def __repr__(self):
        return f"PlayerInformation(player_id={self.player_id}, order={self.order}, card={self.card}, remaining_stack_size={self.remaining_stack_size}, has_folded={self.has_folded})"

class _HiddenCardPlayerInfoProxy:
    """Dict-like proxy that hides one player's card."""
    __slots__ = ('_source', '_hidden_pid')

    def __init__(self, source, hidden_pid):
        self._source = source
        self._hidden_pid = hidden_pid

    def __getitem__(self, key):
        info = self._source[key]
        if key == self._hidden_pid:
            return replace(info, card=-1)
        return info

    def __contains__(self, key):
        return key in self._source

    def __len__(self):
        return len(self._source)

    def __iter__(self):
        return iter(self._source)

    def keys(self):
        return self._source.keys()

    def values(self):
        return [self[pid] for pid in self._source]

    def items(self):
        return [(pid, self[pid]) for pid in self._source]

    def __repr__(self):
        return repr(dict(self.items()))


class _FrozenStateView:
    """Lightweight frozen view of a RoundState with one player's card hidden."""
    __slots__ = ('pot', 'current_bet_total', 'last_raise_delta', 'betting_history',
                 'player_information', '_money_put_in_by_player', '_initialized')

    def __init__(self, source_state, hidden_pid, betting_tuple):
        object.__setattr__(self, '_initialized', False)
        self.pot = source_state.pot
        self.current_bet_total = source_state.current_bet_total
        self.last_raise_delta = source_state.last_raise_delta
        self.betting_history = betting_tuple
        self.player_information = _HiddenCardPlayerInfoProxy(source_state.player_information, hidden_pid)
        self._money_put_in_by_player = source_state._money_put_in_by_player
        object.__setattr__(self, '_initialized', True)

    def __setattr__(self, key, value):
        if getattr(self, '_initialized', False):
            raise AttributeError("Cannot modify frozen state view")
        object.__setattr__(self, key, value)

    def get_money_put_in_by_player(self, player_id: str) -> int:
        return self._money_put_in_by_player.get(player_id, 0)

    def is_player_all_in(self, player_id: str) -> bool:
        return self.player_information[player_id].remaining_stack_size == 0

    def can_check_currently(self, player_id) -> bool:
        return self.get_money_put_in_by_player(player_id) == self.current_bet_total

    def get_delta_to_call_for_player(self, player_id: str) -> int:
        return min(self.player_information[player_id].remaining_stack_size, self.current_bet_total - self.get_money_put_in_by_player(player_id))

    def get_all_in_action_for_player_id(self, player_id: str) -> Action:
        if self.player_information[player_id].remaining_stack_size > self.current_bet_total:
            return Action('raise', player_id=player_id, delta=self.player_information[player_id].remaining_stack_size)
        else:
            return Action('call', player_id=player_id, delta=self.player_information[player_id].remaining_stack_size)

    def get_minimum_raise_delta_for_player(self, player_id: str) -> int:
        call_delta = self.get_delta_to_call_for_player(player_id)
        return max(self.last_raise_delta + call_delta, 1)

    def get_winning_player_id(self) -> str:
        return max([p.player_id for p in self.player_information.values() if not p.has_folded], key=lambda pid: self.player_information[pid].card)

    def check_fold(self, player_id):
        return Action("check") if self.can_check_currently(player_id) else Action("fold")

    def check_call(self, player_id):
        if self.can_check_currently(player_id):
            return Action("check")
        else:
            return Action("call", delta=self.get_delta_to_call_for_player(player_id))

    def __repr__(self):
        return f"_FrozenStateView(pot={self.pot}, current_bet_total={self.current_bet_total})"


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

    def __init__(self, pot: int, player_information: OrderedDict[str, PlayerInformation]):
        self.pot = pot
        self.current_bet_total = 0
        self.last_raise_delta = 0
        self.betting_history = []
        self.player_information = player_information
        self._money_put_in_by_player = {pid: 0 for pid in player_information}
        self._num_folded = 0
        self._num_all_in = 0
        self._betting_tuple_cache = None

    def __setattr__(self, key, value):
        if key != '_frozen' and getattr(self, '_frozen', False):
            raise AttributeError(f"Cannot modify frozen RoundState")
        object.__setattr__(self, key, value)

    def get_state_hiding_card_for_player_id(self, player_id: str):
        """
        Returns a frozen view with the player_id's card hidden from their PlayerInformation.
        """
        if self._betting_tuple_cache is None:
            self._betting_tuple_cache = tuple(self.betting_history)
        return _FrozenStateView(self, player_id, self._betting_tuple_cache)

    def to_frozen(self):
        """
        Returns a frozen copy of this state for safe sharing with strategies.
        """
        new_player_info = OrderedDict(self.player_information)
        new_state = RoundState(pot=self.pot, player_information=new_player_info)
        new_state.current_bet_total = self.current_bet_total
        new_state.last_raise_delta = self.last_raise_delta
        new_state.betting_history = tuple(self.betting_history)
        new_state._money_put_in_by_player = dict(self._money_put_in_by_player)
        new_state.player_information = MappingProxyType(new_player_info)
        new_state._frozen = True
        return new_state

    def get_money_put_in_by_player(self, player_id: str) -> int:
        """
        Returns the total amount of money put in by the player in the current round.
        """
        return self._money_put_in_by_player.get(player_id, 0)

    def is_player_all_in(self, player_id: str) -> bool:
        """
        Returns True if the player is all-in in the current round (and therefore cannot do any actions).
        """
        return self.player_information[player_id].remaining_stack_size == 0

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
        raise_delta = max(self.last_raise_delta + call_delta, 1)
        return raise_delta
    
    def get_winning_player_id(self) -> str:
        """
        Returns the player_id of the winning player in the round.
        """
        return max([player.player_id for player in self.player_information.values() if not player.has_folded], key=lambda pid: self.player_information[pid].card)

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
    """
    Strategy class to represent a player's strategy in the game. You may store state in this and assume that state is not cleared between games or rounds.

    You may also assume that make_decision will be called sequentially as the game progresses
    """
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

    def reveal_round(self, state: RoundState) -> None:
        """
        Called at the end of every round. This is where you can see the final state of the round.
        """
        pass

    def print_state(self) -> str:
        """
        Returns a string representation of the strategy's state. You may use this for debugging purposes.
        """
        return "print_state not implemented"

class IndianPokerGame:
    def __init__(self, strategies: dict[str, Strategy], ante: int, starting_stack: int, logger = logging.getLogger(__name__)):
        """
        Initialize the game with the given strategies, ante, and starting stack sizes.

        Parameters:
        - strategies: A dict of player_id -> Strategy objects representing the players in the game.
        - ante: The ante amount that a player has to pay at the start of each round.
        - starting_stack: The starting stack size for each player.
        - logger: The logger object to use for logging.

        Attributes:
        - stack_sizes: A dict of player_id -> stack_size representing the remaining stack size of each player.
        - historical_stack_sizes: A list of stack_sizes at the end of each round.
        - turn_busted: A dict of player_id -> round_number representing the round number when the player busted.
        - player_id_order: A list of player IDs representing the order of the players.
        - first_player_idx: The index of the first player in the player_id_order list.
        - buster_players: A set of player IDs who have busted (stack size == 0).
        """
        self.strategies = strategies
        self.ante = ante
        self.logger = logger
        self._log_enabled = logger.isEnabledFor(logging.INFO)

        self.stack_sizes = {strategy.player_id: starting_stack for strategy in strategies.values()}
        self.historical_stack_sizes = [ dict( self.stack_sizes ) ]
        self.round_history: list[tuple[RoundState, str]] = [] # (final round_state, logs)
        self.turn_busted = {}
        self.non_busted_player_id_order = [strategy.player_id for strategy in strategies.values()]
        self.busted_players = set()
        random.shuffle(self.non_busted_player_id_order)
        self.next_ante_player_id = self.non_busted_player_id_order[0]

    def make_shuffled_deck(self) -> list[float]:
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

        num_players = len(self.non_busted_player_id_order)
        ante_idx = self.non_busted_player_id_order.index(self.next_ante_player_id)
        non_busted_player_cycle = cycle(self.non_busted_player_id_order)

        # Skip players until we reach the ante payer
        for _ in range(ante_idx):
            next(non_busted_player_cycle)

        # first player pays the entire ante or whatever is left in their stack
        player_id = next(non_busted_player_cycle)
        ante_amount = min(self.stack_sizes[player_id], self.ante)
        self.stack_sizes[player_id] -= ante_amount
        pot += ante_amount

        # the player after the ante payer gets the first card
        for idx in range(num_players):
            player_id = next(non_busted_player_cycle)
            player_information[player_id] = PlayerInformation(
                player_id=player_id,
                order=idx,
                card=deck.pop(),
                remaining_stack_size=self.stack_sizes[player_id]
            )

        # advance ante to the next non-busted player
        self.next_ante_player_id = self.non_busted_player_id_order[(ante_idx + 1) % num_players]

        return RoundState(pot=pot, player_information=player_information)
    
    def setup_round_logger(self) -> tuple[StringIO, logging.Handler]:
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(logging.Formatter('%(message)s'))
        handler.setLevel(logging.INFO)

        self.logger.addHandler(handler)
        self.logger.propagate = False

        return log_stream, handler
    
    def cleanup_round_logger(self, handler: logging.Handler):
        self.logger.removeHandler(handler)
        handler.close()

    def play_round(self) -> RoundState:
        """
        Play starts with the first player and goes in order

        The round ends when
        - all players have folded except one
        - all players have called the current raiser
        - all players have checked
        """
        if self._log_enabled:
            log_stream, stream_handler = self.setup_round_logger()
        else:
            log_stream, stream_handler = None, None
        try:
            # Initial round setup
            round_state = self.get_initial_round_state()
            player_id_cycle = cycle(round_state.player_information.keys())
            num_players = len( round_state.player_information )
            # debug log each player's card
            if self._log_enabled:
                for player_info in round_state.player_information.values():
                    self.logger.info(f"{player_info.player_id} received card: {player_info.card}")

            # Perform betting rounds
            last_bet = False
            player_id = next(player_id_cycle)
            while True:
                need_action = num_players - round_state._num_folded - round_state._num_all_in - (1 if last_bet else 0)
                made_move = 0
                for rep in range( need_action ):
                    # HACK: if everyone folds, you win
                    if round_state._num_folded == num_players - 1:
                        made_move = need_action
                        invalid_action = False
                        break
                    # Skip folded and all-in players
                    while True:
                        player_info = round_state.player_information[player_id]
                        if player_info.has_folded:
                            if self._log_enabled:
                                self.logger.info(f"skipping {player_id} because they have folded")
                            player_id = next( player_id_cycle )
                        elif player_info.remaining_stack_size == 0:
                            if self._log_enabled:
                                self.logger.info(f"skipping {player_id} because they are all-in")
                            player_id = next( player_id_cycle )
                        else:
                            break

                    if self._log_enabled:
                        self.logger.info(f"--- Action on {player_id} ---")
                    action = None
                    try:
                        strategy = self.strategies[player_id]
                        action = strategy.make_decision(round_state.get_state_hiding_card_for_player_id(player_id))
                        action = Action(action.action_type, player_id=player_id, delta=action.delta)
                    except Exception as e:
                        if self._log_enabled:
                            self.logger.exception(f"Error getting decision for {player_id}, folding.")
                        action = Action('fold', player_id=player_id)

                    # Process action
                    invalid_action = False
                    if action.action_type == 'fold':
                        if self._log_enabled:
                            self.logger.info(f"{player_id} folds.")
                        round_state.player_information[player_id] = replace(player_info, has_folded=True)
                        round_state._num_folded += 1

                    elif action.action_type == 'call':
                        call_delta = action.delta
                        if call_delta == 0:
                            if self._log_enabled:
                                self.logger.info(f"{player_id} folds due to a call amount of 0")
                            invalid_action = True
                        elif call_delta != round_state.get_delta_to_call_for_player(player_id):
                            if self._log_enabled:
                                self.logger.info(f"{player_id} folds due to invalid call amount.")
                            invalid_action = True
                        elif call_delta > round_state.player_information[player_id].remaining_stack_size:
                            if self._log_enabled:
                                self.logger.info(f"{player_id} folds due to stack size too small.")
                            invalid_action = True
                        else:
                            info = round_state.player_information[player_id]
                            round_state.player_information[player_id] = replace(info, remaining_stack_size=info.remaining_stack_size - call_delta)
                            round_state.pot += call_delta
                            round_state._money_put_in_by_player[player_id] += call_delta
                            if info.remaining_stack_size - call_delta == 0:
                                round_state._num_all_in += 1
                            if self._log_enabled:
                                self.logger.info(f"{player_id} calls {call_delta}.")

                    elif action.action_type == 'raise':
                        call_and_raise_delta = action.delta # this includes the amount needed to call as well
                        if call_and_raise_delta < round_state.get_minimum_raise_delta_for_player(player_id):
                            if self._log_enabled:
                                self.logger.info(f"{player_id} folds due to invalid raise amount.")
                            invalid_action = True
                        elif call_and_raise_delta > round_state.player_information[player_id].remaining_stack_size:
                            if self._log_enabled:
                                self.logger.info(f"{player_id} folds due to stack size too small.")
                            invalid_action = True
                        else:
                            player_current_bet = round_state.get_money_put_in_by_player(player_id)
                            call_delta = round_state.get_delta_to_call_for_player(player_id) # this is the amount needed to call
                            raise_delta = call_and_raise_delta - call_delta # this is the amount raised

                            round_state.pot += call_and_raise_delta
                            round_state.last_raise_delta = raise_delta
                            round_state.current_bet_total = player_current_bet + call_delta + raise_delta
                            info = round_state.player_information[player_id]
                            round_state.player_information[player_id] = replace(info, remaining_stack_size=info.remaining_stack_size - call_and_raise_delta)
                            round_state._money_put_in_by_player[player_id] += call_and_raise_delta
                            if info.remaining_stack_size - call_and_raise_delta == 0:
                                round_state._num_all_in += 1

                            if self._log_enabled:
                                self.logger.info(f"{player_id} raises {raise_delta} (call {call_delta}) to the pot for a total bet of {round_state.current_bet_total}.")

                    elif action.action_type == 'check':
                        if not round_state.can_check_currently(player_id):
                            if self._log_enabled:
                                self.logger.info(f"{player_id} folds due to invalid check.")
                            invalid_action = True
                        else:
                            if self._log_enabled:
                                self.logger.info(f"{player_id} checks.")

                    else:
                        if self._log_enabled:
                            self.logger.info(f"{player_id} folds due to invalid action type.")
                        invalid_action = True

                    acting_player_id = player_id
                    player_id = next( player_id_cycle )
                    # Record the action
                    if not invalid_action:
                        round_state.betting_history.append(action)
                        round_state._betting_tuple_cache = None
                        if action.action_type != 'raise':
                            made_move += 1
                        else:
                            last_bet = True
                            break
                    else:
                        round_state.player_information[acting_player_id] = replace(
                            round_state.player_information[acting_player_id], has_folded=True
                        )
                        round_state._num_folded += 1
                        round_state.betting_history.append(Action('fold', player_id=acting_player_id))
                        round_state._betting_tuple_cache = None
                        made_move += 1

                if made_move == need_action:
                    break

            # Determine the winner and distribute pot with side pot logic
            remaining_players = [pid for pid in round_state.player_information if not round_state.player_information[pid].has_folded]

            if len(remaining_players) == 1:
                winner = remaining_players[0]
                if self._log_enabled:
                    self.logger.info(f"{winner} wins the pot of {round_state.pot} by default.")
                for pid in round_state.player_information:
                    if pid == winner:
                        self.stack_sizes[pid] = round_state.player_information[pid].remaining_stack_size + round_state.pot
                    else:
                        self.stack_sizes[pid] = round_state.player_information[pid].remaining_stack_size
            else:
                # Side pot distribution: each player can only win from each opponent
                # up to the amount they themselves put in
                contributions = round_state._money_put_in_by_player

                # Start each player with their remaining stack
                for pid in round_state.player_information:
                    self.stack_sizes[pid] = round_state.player_information[pid].remaining_stack_size

                # Sort remaining players by contribution (lowest first) for side pot calculation
                sorted_remaining = sorted(remaining_players, key=lambda pid: contributions[pid])

                # Build and resolve side pots
                already_claimed = 0
                for i, claimant in enumerate(sorted_remaining):
                    claimant_contrib = contributions[claimant]
                    eligible_amount = claimant_contrib - already_claimed
                    if eligible_amount <= 0:
                        continue

                    # This player can claim up to eligible_amount from each player
                    side_pot = 0
                    for pid in round_state.player_information:
                        collectible = min(contributions[pid], claimant_contrib) - min(contributions[pid], already_claimed)
                        side_pot += collectible

                    # Winner of this side pot is the remaining player (from this point onward) with the highest card
                    eligible_winners = sorted_remaining[i:]
                    side_pot_winner = max(eligible_winners, key=lambda pid: round_state.player_information[pid].card)
                    self.stack_sizes[side_pot_winner] += side_pot
                    if self._log_enabled:
                        self.logger.info(f"{side_pot_winner} wins side pot of {side_pot}.")

                    already_claimed = claimant_contrib

                # Any remainder (from folded players who put in more than all remaining) goes to highest card
                total_distributed = sum(self.stack_sizes[pid] - round_state.player_information[pid].remaining_stack_size for pid in round_state.player_information)
                remainder = round_state.pot - total_distributed
                if remainder > 0:
                    top_player = max(remaining_players, key=lambda pid: round_state.player_information[pid].card)
                    self.stack_sizes[top_player] += remainder
                    if self._log_enabled:
                        self.logger.info(f"{top_player} wins remainder of {remainder}.")

            if self._log_enabled:
                self.logger.info(f"Stack Sizes: {self.stack_sizes}")
            self.historical_stack_sizes.append( dict( self.stack_sizes ) )

            # update busted players
            for pid in self.stack_sizes:
                if self.stack_sizes[pid] == 0 and pid not in self.busted_players:
                    self.busted_players.add(pid)
                    # if the next ante player busted, advance to the next one
                    if pid == self.next_ante_player_id and len(self.non_busted_player_id_order) > 1:
                        idx = self.non_busted_player_id_order.index(pid)
                        self.next_ante_player_id = self.non_busted_player_id_order[(idx + 1) % len(self.non_busted_player_id_order)]
                    self.non_busted_player_id_order.remove(pid)
                    self.turn_busted[pid] = len(self.historical_stack_sizes)

            # Call reveal_round for each strategy that participated in this round
            frozen_state = round_state.to_frozen()
            for strategy in self.strategies.values():
                if strategy.player_id not in round_state.player_information:
                    continue
                try:
                    strategy.reveal_round(frozen_state)
                except Exception as e:
                    if self._log_enabled:
                        self.logger.exception(f"Error calling reveal_round for {strategy.player_id}")

            self.round_history.append( (round_state, log_stream.getvalue() if log_stream else "") )
            return round_state
        finally:
            if stream_handler is not None:
                self.cleanup_round_logger(stream_handler)

    def has_at_least_2_players_left(self):
        return len(self.stack_sizes) - len(self.busted_players) >= 2

def simulate_game(strategies: dict[str, Strategy], ante: int, starting_stack: int, rounds: int, logger = logging.getLogger(__name__)) -> IndianPokerGame:
    game = IndianPokerGame(strategies, ante, starting_stack, logger=logger)
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
