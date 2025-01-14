import math
import numpy as np
from random import randint

# Concerns: Add epsilon amount to UCB evaluation to ensure probability is considered
# Caveat: Q in heuristic might obviate this.
# Concerns: No Dir noise being added. If it is added, tests would break.
# Caveat: Make Dir a switch, write tests that use Dir with fixed seed.


# An efficient, vectorized Monte Carlo tree search implementation.
# Uses no loops, done completely with numpy.
class MCTS():

    def __init__(self, game, nn):
        self.game = game
        self.nn = nn
        self.tree = {}
        self.debug_stats = []

    # Produces a hash-friendly representation of an ndarray.
    # This is used to index nodes in the accumulated Monte Carlo tree.
    def np_hash(self, data):
        return data.tostring()

    # Run a MCTS simulation starting from state s of the tree.
    # The tree is accumulated in the self.tree dictionary.
    # The epsilon fix prevents the U term from being 0 when unexplored (N=0).
    # With the fix, priors (P) can be factored in immediately during selection and expansion.
    # This makes the search more efficient, given there are strong priors.
    def simulate(self, s, cpuct=1, epsilon_fix=True, level=0):
        hashed_s = self.np_hash(s) # Key for state in dictionary
        current_player = self.game.get_player(s)
        if hashed_s in self.tree: # Not at leaf; select.
            stats = self.tree[hashed_s]
            N, Q, P = stats[:,1], stats[:,2], stats[:,3]
            U = cpuct*P*math.sqrt(N.sum() + (1e-6 if epsilon_fix else 0))/(1 + N)
            heuristic = Q + U
            best_a_idx = np.argmax(heuristic)
            best_a = stats[best_a_idx, 0] # Pick best action to take
            template = np.zeros_like(self.game.get_available_actions(s)) # Submit action to get s'
            template[tuple(best_a)] = True
            s_prime = self.game.take_action(s, template)
            scores = self.simulate(s_prime, level=level+1) # Forward simulate with this action
            n, q = N[best_a_idx], Q[best_a_idx]
            v = scores[current_player] # Index in to find our reward
            stats[best_a_idx, 2] = (n*q+v)/(n + 1)
            stats[best_a_idx, 1] += 1
            return scores

        else: # Expand
            scores = self.game.check_game_over(s)
            self.debug_stats.append((level, scores))
            if scores is not None: # Reached a terminal node
                return scores
            available_actions = self.game.get_available_actions(s)
            idx = np.stack(np.where(available_actions)).T
            p, v = self.nn.predict(s)
            stats = np.zeros((len(idx), 4), dtype=np.object)
            stats[:,-1] = p
            stats[:,0] = list(idx)
            self.tree[hashed_s] = stats
            return v


    # Returns the MCTS policy distribution for state s.
    # The temperature parameter softens or hardens this distribution.
    def get_distribution(self, s, temperature):
        hashed_s = self.np_hash(s)
        stats = self.tree[hashed_s][:,:2].copy()
        N = stats[:,1]
        try:
            raised = np.power(N, 1/temperature)
        # As temperature approaches 0, the effect becomes equivalent to argmax.
        except (ZeroDivisionError, OverflowError):
            raised = np.zeros_like(N)
            raised[N.argmax()] = 1
        
        total = raised.sum()
        # If all children are unexplored, prior is uniform.
        if total == 0:
            raised[:] = 1
            total = raised.sum()
        dist = raised/total
        stats[:,1] = dist
        return stats
        

# Standard MCTS that does a random rollout at the leaf rather than calling a neural network
class RolloutMCTS(MCTS):
    def __init__(self, game):
        super(RolloutMCTS, self).__init__(game, None)

    
    # Run a MCTS simulation starting from state s of the tree.
    # The tree is accumulated in the self.tree dictionary.
    # The epsilon fix prevents the U term from being 0 when unexplored (N=0).
    # With the fix, priors (P) can be factored in immediately during selection and expansion.
    # This makes the search more efficient, given there are strong priors.
    def simulate(self, s, cpuct=1, epsilon_fix=True, level=0):
        hashed_s = self.np_hash(s) # Key for state in dictionary
        current_player = self.game.get_player(s)
        if hashed_s in self.tree: # Not at leaf; select.
            stats = self.tree[hashed_s]
            N, Q, P = stats[:,1], stats[:,2], stats[:,3]
            U = cpuct*P*math.sqrt(N.sum() + (1e-6 if epsilon_fix else 0))/(1 + N)
            heuristic = Q + U
            best_a_idx = np.argmax(heuristic)
            best_a = stats[best_a_idx, 0] # Pick best action to take
            template = np.zeros_like(self.game.get_available_actions(s)) # Submit action to get s'
            template[tuple(best_a)] = True
            s_prime = self.game.take_action(s, template)
            scores = self.simulate(s_prime, level=level+1) # Forward simulate with this action
            n, q = N[best_a_idx], Q[best_a_idx]
            v = scores[current_player] # Index in to find our reward
            stats[best_a_idx, 2] = (n*q+v)/(n + 1)
            stats[best_a_idx, 1] += 1
            return scores

        else: # Expand by getting rollout result for the leaf
            s_rollout = s.copy()
            scores = self.game.check_game_over(s_rollout)
            if scores is None: # not at a terminal node
                # do random rollout
                while scores is None:
                    available_actions = self.game.get_available_actions(s_rollout)
                    template = np.zeros_like(available_actions)
                    # pick an action at random
                    action_idx = available_actions.nonzero()[0]
                    action = action_idx[randint(0, action_idx.shape[0]-1)]
                    template[action] = True               
                    s_rollout = self.game.take_action(s_rollout, template)
                    scores = self.game.check_game_over(s_rollout)
                
                available_actions = self.game.get_available_actions(s)
                idx = np.stack(np.where(available_actions)).T
                stats = np.zeros((len(idx), 4), dtype=np.object)
                stats[:,-1] = np.ones(len(idx), dtype=np.float32)
                stats[:,0] = list(idx)
                self.tree[hashed_s] = stats

            return scores