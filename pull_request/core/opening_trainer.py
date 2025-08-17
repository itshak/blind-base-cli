import sys
import numpy as np
from pdb import set_trace
import json 
import time

from scipy.special import softmax
import time
import chess

from blindbase.core.opening_tree import get_master_moves
from blindbase.analysis import select_move_candidates
from blindbase.core.navigator import GameNavigator
from blindbase.core.pgn import GameManager

from blindbase.merge_games import find_variation
from blindbase.merge_games import store_game

import logging

def setup_logger():
    logging.basicConfig(filename='trainer.log', 
                        encoding='utf-8', 
                        level=logging.DEBUG) 
#end of setup_logger()

def disable_ssl_verification():
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
#end of disable_ssl_verification()

def cp_score(score, side):
    return score.pov(side).score(mate_score=10000)
#end of cp_score()

def parse_move_san(board, move_san):
    try:
        move = board.parse_san(move_san)
    except ValueError:
        return None
    #end of try/except
    return move
#end of parse_move_san()

def load_engine(engine_path):
    #from blindbase.core.engine import Engine
    print(f"Using Engine: {engine_path}")
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    except FileNotFoundError:
        sys.stderr.write('Error: engine not found at %s\n'% (engine_path))
        sys.exit(1)
    except Exception as e:
        sys.stderr.write('Error initializing engine: %s\n' %(str(e)))
        sys.exit(1)
    #end of try/except
    return engine
#end of load_engine()

def retrieve_move_stats(stat_client, board):
    if stat_client is None:
        return [ ]
    #end of if
    lst = get_master_moves(board)
    res = [ (parse_move_san(board, tup[0]),sum(tup[1:])) for tup in lst ]
    return res
#end of retrive_move_stats()


def load_game(inp_fn):
    gm = GameManager(inp_fn)
    return gm.games[0]
#end of load_game()



class k_unit:
    def __init__(self, conf):
        self.stat = conf.get('stat', 0)  # general game statistics 
        self.ext_stat = conf.get('ext_stat', 0)  # general game statistics out of tree
        self.hist = conf.get('hist','') # observation history
        self.belief = conf.get('belief', 0.1) # current belief, we know the move
        self.guess = conf.get('guess', 0.1) # probability to guess the move 
        self.ts = conf.get('ts', int(time.time()))
        self.max_score = conf.get('max_score', None) # SF score for best move
        self.ext_score = conf.get('ext_score', None) # expected SF score out of tree
        self.opt_score = conf.get('opt_score', None) # expected recursive score, assuming all hits
        self.exp_score = conf.get('exp_score') # expected_score
        self.prob = conf.get('prob') # prob. to take the move
        self.gain = conf.get('gain', None) # current gain of information 
        if self.prob is None and self.belief is not None:
            self.update_prob()
        #end of if
    #end of __init__()

    def update_prob(self):
        self.prob = self.belief + (1.0 - self.belief) * self.guess
        self.ts = int(time.time())
      #end of update_prob()

    def add_observation(self, obs):
        self.hist += ('h' if obs else 'm')
        # p(x|yz) = 
        # p(yz|x)p(x)/P(yz) = 
        #p(y|x)p(x|z)p(z)/p(yz) = 
        #p(y|x)p(x|z)/p(y|z) =
        # p(y|x)p(x|z) / (p(y|x)p(x|z) + p(y|!x)p(!x|z))
        prior = self.belief
        post = prior / (prior + (1.0 - prior) * self.guess) if obs else 0.0
        self.belief = post
        self.update_prob()
    #end of add_observation()

    def upgrade(self, lrate):
        self.hist += 'u'
        prev = self.belief
        self.belief = prev + (1.0 - prev) * lrate
        self.update_prob()
        #print('belief: %f -> %f lrate:%f' %(prev, self.belief, lrate))
    #end of upgrade()

    def degrade(self, lrate):
        self.hist += 'd'
        self.belief *= (1.0 - lrate)
        self.update_prob()
    #end of degrade()

    def get_prop_gain(self):
        return self.prob * self.gain
    #end of get_prop_gain()
    
    def to_formal_string(self):
        dct = { 
               'stat' :self.stat, 
               'ext_stat':self.ext_stat, 
               'max_score':self.max_score, 
               'ext_score':self.ext_score, 
               'opt_score':self.opt_score, 
               'exp_score':self.exp_score, 
               'guess':self.guess, 
               'belief':self.belief, 
               'prob':self.prob,
               'gain':self.gain,
               'ts':self.ts,
               'hist':self.hist
               }
        buf = json.dumps(dct)
        return buf[1:-1] # without {}

    #end of to_formal_string()

    def read_from_formal_string(self, buf):
        dct = json.loads('{'+buf+'}')
        self.__init__(dct)
    #end of read_from_formal_string()
#end of class k_unit




class OpeningTrainer(GameNavigator):
    def __init__(self, conf, game=None):
        setup_logger()
        self.logger = logging.getLogger(__name__)
        self.logger.debug('Creating OpeningTrainer object')
        self.conf = conf
        my_side = conf.get('my_side', 'white')
        self.my_side = chess.WHITE if my_side == 'white' else chess.BLACK
        self.lrate = conf.get('lrate', 0.9)
        self.drate = conf.get('drate', 0.1)
        self.opt_method = conf.get('opt_method')
        if not game:
            game = chess.pgn.Game()
            game.setup(chess.Board())
            #game.comment = k_unit(self.conf)
        #end of if
        super().__init__(game)
        #end of if
    #end of __init__()

    def print_all_lines(self, pref='', node=None):
        if node is None:
            node = self._root
        #end of if
        if not node.variations:
            print(pref)
            return
        #end of if
        for var in node.variations:
            next_pref = pref + node.board().san(var.move) + ' '
            self.print_all_lines(next_pref, var)
        #end of for
    #end of print_all_lines()

    def print_all_scores(self, node=None):
        if node is None:
            node = self._root
            print('::: %s : %s :::' %(str(self.my_side), str(node.board().turn)))
        #end of if
        if not node.variations:
            print('------')
            return
        #end of if
        for var in node.variations:
            move_san = node.board().san(var.move)
            rec = var.comment
            turn = str(var.board().turn)
            obs = '"' + rec.hist + '"'
            gain = 'None' if rec.gain is None else '%.6f' %(rec.gain)
            print('%s %s : %.2f %.2f opt: %.4f bel: %.6f gain: %s %s' %(move_san, turn, rec.max_score, rec.ext_score, rec.opt_score, rec.belief, gain, obs))
            self.print_all_scores(var)
        #end of for
    #end of print_all_scores()

    def is_my_turn(self, node=None):
        if node is None:
            node = self._node
        #end of if
        return (node.board().turn == self.my_side)
    #end of is_my_turn()

    def archivate(self, node=None):
        if node is None:
            node = self._root
        #end of if
        node.comment = node.comment.to_formal_string()
        for var in node.variations:
            self.archivate(var)
        #end of for
    #end of archivate()

    def dearchivate(self, node=None):
        if node is None:
            node = self._root
        #end of if
        buf = node.comment
        node.comment = k_unit({})
        node.comment.read_from_formal_string(buf)
        for var in node.variations:
            self.dearchivate(var)
        #end of for
    #end of dearchivate()

    def store(self, out_fn):
        self.logger.debug('store() to file %s' %(out_fn))
        self.archivate(self._root)
        res = store_game(self._root, out_fn)
        self.dearchivate()
        return res
    #end of store()

    def load(self, inp_fn):
        game = load_game(inp_fn)
        if game is None:
            return False
        #end of if
        super().__init__(game)
        #self.dearchivate()
        return True
    #end of load()

    def add_game(self, src_node, tar_node=None):
        if tar_node is None:
            tar_node = self._root
        #end of if
        rec = tar_node.comment
        is_my_turn = (tar_node.board().turn == self.my_side)
        for src_var in src_node.variations:
            next_tar = find_variation(tar_node, src_var.move)
            if next_tar is None:
                # a new src move
                if is_my_turn and tar_node.variations:
                    sys.stderr.write('Cannot add my move: %s\n' %(str(src_var.move)))
                    continue
                #end of if
                next_tar = tar_node.add_variation(src_var.move)
                next_tar.comment = src.var.comment
            #end of if
            self.add_game(src_var, next_tar)
        #end of for src_var
    #end of add_game()

    def compute_var_distrib(self, node, conf):
        bfact = conf.get('score_factor', 1.0)
        cfact = conf.get('count_factor', 1.0)
        rec = node.comment
        if rec.ext_score is None:
            scores = [ var.comment.max_score for var in node.variations ]
            cnts = [ var.comment.stat for var in node.variations ]
        else:
            scores = [ var.comment.max_score for var in node.variations ] + [ rec.ext_score] 
            cnts = [ var.comment.stat for var in node.variations ] + [ rec.ext_stat ]
        #end of if/else
        score_cnts = softmax(bfact * np.array(scores))
        cmb_cnts = score_cnts + cfact * np.array(cnts)
        probs = cmb_cnts / cmb_cnts.sum()
        for i,var in enumerate(node.variations):
            var.comment.prob = probs[i]
        #end of for
        if rec.ext_score is not None:
            probs = probs[:-1]
        #end of if
        return probs
    #end of compute_var_distrib()

    def compute_stats(self, node, stat_client):
        if not node.variations:
            return
        #end of if
        board = node.board()
        stats = retrieve_move_stats(stat_client, board)
        move_cnts = dict(stats)
        for var in node.variations:
            var.comment.stat = move_cnts.get(var.move, 0)
        #end of for

        var_moves = set([ var.move for var in node.variations])
        rem_cnts = [ y[1] for y in filter(lambda x: x[0] not in var_moves, stats) ]
        node.comment.ext_stat = sum(rem_cnts) if rem_cnts else 0
    #end of compute_stats()

    def setup_stats(self, stat_client, node=None):
        if node is None:
            node = self._root
        #end of if
        for var in node.variations:
            self.setup_stats(stat_client, var)
        #end of for
        self.compute_stats(node, stat_client)
    #end of setup_stats()

    def compute_local_scores(self, node, engine):
        MY_WINDOW=3 # window of additional moves for ext_score
        OP_WINDOW=1
        board = node.board()
        is_my_turn = (board.turn == self.my_side)
        def_window = MY_WINDOW if is_my_turn else OP_WINDOW
        num = len(node.variations)
        cands,depth = select_move_candidates(engine, board, def_window + num)
        node.comment.max_score = cp_score( cands[0][1], self.my_side)
        moves = set([ var.move for var in node.variations ])
        rem_scores = [ cp_score(x[1], self.my_side) for x in filter(lambda x: x[0] not in moves, cands) ]
        node.comment.ext_score = np.mean(rem_scores[:def_window]) if rem_scores else None
    #end of compute_local_scores()

    def setup_local_scores(self, engine, node=None):
        if node is None:
            node = self._root
        #end of if
        for var in node.variations:
            self.setup_local_scores(engine, var)
        #end of for
        self.compute_local_scores(node, engine)
    #end of setup_local_scores()

    def compute_opt_score(self, node, conf):
        if not node.variations:
            node.comment.opt_score = node.comment.max_score
            return
        #end of if
        is_my_turn = (node.board().turn == self.my_side)
        if is_my_turn:
            node.comment.opt_score = node.variations[0].comment.opt_score
            return
        #end of if
        scores = [ var.comment.opt_score for var in node.variations ]
        ext_score = node.comment.ext_score
        probs = self.compute_var_distrib(node, conf)
        prod = (probs * np.array(scores)).sum()
        if ext_score is not None:
            def_prob = 1.0 - probs.sum()
            prod = prod + def_prob * ext_score 
        #end of if
        node.comment.opt_score = prod
    #end of compute_opt_score()

    def setup_opt_scores(self, conf, node=None):
        if node is None:
            node = self._root
        #end of if
        for var in node.variations:
            self.setup_opt_scores(conf, var)
        #end of for
        self.compute_opt_score(node. conf)
    #end of setup_opt_scores()

    def compute_exp_score(self, node):
        if node.comment.exp_score is not None:
            return
        #end of if
        if not node.variations:
            node.comment.exp_score = node.comment.max_score
            return
        #end of if
        for var in node.variations:
            self.compute_exp_score(var)
        #end of for
        scores = np.array([ var.comment.exp_score for var in node.variations ])
        probs = np.array([ var.comment.prob for var in node.variations ])
        ext_score = node.comment.ext_score
        prod = (probs * scores).sum()
        if ext_score is not None:
            def_prob = 1.0 - probs.sum()
            prod = prod + def_prob * ext_score 
        #end of if
        node.comment.exp_score = prod
    #end of compute_exp_score()

    def setup_all_scores(self, conf, engine, stat_client, node=None):
        if node is None:
            node = self._root
        #end of if
        for var in node.variations:
            self.setup_all_scores(conf, engine, stat_client, var)
        #end of for
        node.comment = k_unit( conf)
        self.compute_local_scores(node, engine)
        self.compute_stats(node, stat_client)
        self.compute_opt_score(node, conf)
        self.compute_exp_score(node)
    #end of setup_all_scores()

    def invalidate_gain_down(self, node=None):
        if node is None:
            node = self._root
        #end of if
        for var in node.variations:
            self.invalidate_gain_down(var)
        #end of for
        node.comment.gain = None
        node.comment.exp_score = None
    #end of invalidate_gain_down()

    def invalidate_gain_up(self, node=None):
        if node == None:
            node = self._node
        #end of if
        while node is not None:
            if node.comment.gain is None:
                break
            #end of if
            node.comment.gain = None
            node.comment.exp_score = None
            node = node.parent
        #end of while
    #end of invalidate_gain_up()

    def add_observation_line(self, line):
        self.logger.debug('add_observation_line(): %s' %(str(line)))
        tar_node = self._root
        src_node = line
        while ( tar_node.variations and src_node.variations):
            is_my_turn = (tar_node.board().turn == self.my_side)
            if is_my_turn:
                next_tar = tar_node.variations[0]
                next_src = find_variation(src_node, next_tar.move)
                if next_src is None:
                    sys.stderr.write('No correct move in observation line: %s\n' %(str(next_tar.move)))
                    sys.stderr.write('moves in obs. line: %s\n' % (' , '.join([ str(x.move) for x in src_node.variations])))
                    return False
                #end of if
                is_hit = ( len(src_node.variations)==1 )
                next_tar.comment.add_observation(is_hit)
                next_tar.comment.upgrade(self.lrate)
                self.invalidate_gain_up(tar_node)
            else: # not is_my_turn
                next_src = src_node.variations[0]
                next_tar = find_variation(tar_node, next_src.move)
                if next_tar is None:
                    sys.stderr.write('Unknown move in observation line: %s\n' %(str(next_src.move)))
                    sys.stderr.write('Existing moves in obs. line: %s\n' % (' , '.join([ str(x.move) for x in tar_node.variations])))
                    return False
                #end of if
            #end of if/else
            src_node = next_src
            tar_node = next_tar
        #end of while
        return not(src_node.variations)
    #end of add_observation_line()

    def compute_local_gain(self, node):
        rec = node.variations[0].comment
        if  node.comment.ext_score is None:
            return 0
        #end of if
        exp_score = (rec.exp_score + rec.gain) if self.opt_method=='mlg' else rec.opt_score 
        ext_score = min(node.comment.ext_score, exp_score)
        return (1.0 - rec.prob) * (exp_score - ext_score)
    #end of compute_local_gain()

    def compute_gain(self, node=None):
        if node is None:
            node = self._root
        #end of if
        self.compute_exp_score(node)
        rec = node.comment
        is_my_turn = (node.board().turn == self.my_side)
        if rec.gain is not None:
            return rec.gain
        #end of if
        if not node.variations:
            rec.gain = 0.0
        elif is_my_turn:
            next_node = node.variations[0]
            self.compute_gain(next_node)
            rec.gain = self.compute_local_gain(node) + next_node.comment.get_prop_gain()
        else:
            for var in node.variations:
                self.compute_gain(var)
            #end of for
            cands = [ var.comment.get_prop_gain() for var in node.variations ]
            rec.gain = np.max( cands ) if self.opt_method in ['mlr','mlg'] else np.sum(cands)
        #end of if/else
        return rec.gain
    #end of compute_gain()

    def select_max_gain_candidates(self, node=None):
        if node is None:
            node = self._node
        #end of if
        if not node.variations:
            return []
        #end of if
        if node.comment.gain is None:
            self.compute_gain(node)
        #end of if
        is_my_turn = (node.board().turn == self.my_side)
        if is_my_turn:
            move = node.variations[0].move
            return [ (node.board().san(move), node.comment.gain)]
        #end of if
        return [ (node.board().san(var.move), var.comment.get_prop_gain()) for var in node.variations ]
    #end of select_max_gain_candidates()

    def select_opponent_move(self, node=None):
        if node is None:
            node = self._node
        #end of if
        if not node.variations:
            return None
        #end of if
        if node.comment.gain is None:
            self.compute_gain(node)
        #end of if
        if node.board().turn == self.my_side:
            self.logger.warning('It is not the opponent turn')
            return None
        #end of if
        cands = [ var.comment.get_prop_gain() for var in node.variations ]
        i = np.argmax(cands)
        move = node.variations[i].move
        move_san = node.board().san(move)
        return move_san
    #end of select_opponent_move()
    
    def select_max_gain_line(self, node=None):
        if node is None:
            node = self._root
        #end of if
        if node.comment.gain is None:
            self.compute_gain(node)
        #end of if
        line = []
        while node.variations:
            is_my_turn = (node.board().turn == self.my_side)
            if is_my_turn or len(node.variations)==1:
                node = node.variations[0]
            else:
                cands = [ var.comment.get_prop_gain() for var in node.variations ]
                i = np.argmax(cands)
                self.logger.debug('%s -> %d' %(str(cands), i))
                node = node.variations[i]
            #end of if/else
            line.append(node.move)
        #end of while
        return line
    #end of select_max_gain_line()

    def go_root(self):
        self._node = self._root
    #end of go_root()
    

    def review_my_move(self, lrate=None):
        node = self._node
        is_my_turn = (node.board().turn == self.my_side)
        if not is_my_turn:
            self.logger.warning('It is not my turn')
            return None
        #end of if
        if not node.variations:
            self.logger.warning('No next move is defined')
            return None
        #end of if
        next_node = node.variations[0]
        if lrate is None:
            lrate = self.lrate
        #end of if
        next_node.comment.upgrade(lrate)
        self.invalidate_gain_up(node)
        move = next_node.move
        move_san = node.board().san(move)
        self._node = next_node
        self.logger.debug('review_my_move() for move: %s with lrate=%.2f' %(move_san, lrate))
        return move_san
    #end of review_my_move()

    def review_line(self, line, lrate=None):
        node = self._root
        if lrate is None:
            lrate = self.lrate
            #print('lrate: %f' %(lrate))
        #end of if
        is_my_turn = (node.board().turn == self.my_side)
        for move in line:
            if not node.variations:
                self.logger.warning('No next move is defined')
                return False
            #end of if
            if is_my_turn:
                node = node.variations[0]
                if node.move != move:
                    self.logger.warning('Wrong my move in line: %s' %(str(move)))
                    return False
                #end of if
                node.comment.upgrade(lrate)
                self.invalidate_gain_up(node)
            else:
                node = find_variation(node, move)
                if node is None:
                    self.logger.warning('Wrong move in line: %s' %(str(move)))
                    return False
                #end of if
            #end of if/else
            is_my_turn = not(is_my_turn)
        #end of while
        return True
    #end of review_line()

    def submit_my_move(self, move):
        node = self._node
        self.logger.debug('submit_my_move() %s' %(str(move)))
        if (node.board().turn != self.my_side):
            self.loggerwarning('It is not my move')
            return False
        #end of if
        if not node.variations:
            self.logger.warning('No next move is defined')
            return False
        #end of if
        next_node = node.variations[0]
        is_hit = (move == next_node.move)
        next_node.comment.add_observation(is_hit)
        self.invalidate_gain_up(node)
        return is_hit
    #end of submit_my_move()

    def is_at_eol(self):
        return not (self._node.variations)
    #end of is_at_eol()

    def go_forward(self, move_san):
        node = self._node
        if not node.variations:
            sys.stderr.write('No next move exists\n')
            return False
        #end of if
        if not move_san:
            self._node = node.variations[0]
            return True
        #end of if
        move = parse_move_san(node.board(), move_san)
        if move is None:
            sys.stderr.write('Error: wrong move: %s\n' %(str(move_san)))
            return False
        #end of if
        next_node = find_variation(node, move)
        self._node = next_node
        return True
    #end of go_forward()

    def get_line_san(self, line):
        return self._root.board().copy().variation_san(line)
    #end of get_line_san()


#end of OpeningTrainer class

def trainer_test(trainer, conf):
    print('loaded lines:')
    print('------------')
    trainer.print_all_lines()
    print('------------')
    num_test_steps = conf.get('num_test_steps', 3)

    for i in range(1,num_test_steps+1):
        print('step: %d' %(i))
        val = trainer.compute_gain()
        print('gain: %f' %(val))
        line = trainer.select_max_gain_line()
        line_san = trainer.get_line_san(line)
        print(line_san)
        trainer.review_line(line)
        out_fn = 'step-%d.pgn' %(i)
        trainer.store(out_fn)
    #end of for i
    return True
#end of trainer_test()

def trainer_test2(trainer, conf):

    for i in range(10):
        if trainer.is_at_eol():
            sys.stderr.write('EOL is reached\n')
            break
        #end of if
        if trainer.is_my_turn():
            res = trainer.submit_my_move(None)
            print('submit_my_move("") -> %s' %(str(res)))
            move_san = trainer.review_my_move()
            print('review_my move() -> %s' %(str(move_san)))
        else:
            cands = trainer.select_max_regret_candidates()
            if not cands:
                print('EOL is reached')
                break
            #end of if
            print('Next move candidates:')
            for move_san,val in cands:
                print('%s - %s' %(move_san, str(val)))
            #end of for
            move_san = trainer.select_opponent_move()
            print('max_regret move: %s' %(str(move_san)))
            res = trainer.go_forward(move_san)
            if not res:
                sys.stderr.write('go_forward() is Failed with move: %s\n' %(str(move_san)))
                break
            #end of if
        #end of if/else
    #end of for
    #trainer.store('step1.pgn')
    val = trainer.compute_gain()
    print('max_regret: %f' %(val))
    #trainer.print_all_scores()
    return True
#end of trainer_test2()

if __name__=='__main__':
    argc = len(sys.argv)
    conf_path = sys.argv[1]
    pgn_fn = sys.argv[2]
    engine_path = sys.argv[3] if argc > 3 else None
    stat_client = sys.argv[4] if argc >4 else None
    if conf_path[0] == '{':
        conf = json.loads(conf_path)
    else: 
        conf = json.load(open(conf_path))
    #end of if/else
                                                    

    engine = load_engine(engine_path) if engine_path else None

    gm = GameManager(pgn_fn)
    trainer = OpeningTrainer(conf, gm.games[0])
    #res = trainer.load( pgn_fn)
    #if not res:
    #    sys.stderr.write('Failed to load trainer from file: %s\n' %(pgn_fn))
    #    sys.exit(1)
    #end of if
    for game in gm.games[1:]:
                         trainer.add_game(game)
                        #end of for
    if engine is None:
        print('Calling to dearchivate()')
        trainer.dearchivate()
    else:
        disable_ssl_verification()
        print('calling to setup_all_scores()')
        trainer.setup_all_scores(conf, engine, stat_client)
    #end of if/else

    trainer.compute_gain()
    trainer.store('start1.pgn')
    res = trainer_test(trainer, conf)
    print('test_trainer() -> %s' %(str(res)))

    sys.exit(0)
#end of if
