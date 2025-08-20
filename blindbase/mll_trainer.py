import sys
import numpy as np
from pdb import set_trace

from scipy.special import softmax
import time
import chess

from blindbase.core.opening_tree import get_master_moves
from blindbase.analysis import select_move_candidates
from blindbase.core.navigator import GameNavigator
from blindbase.core.pgn import GameManager

def disable_ssl_verification():
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
#end of disable_ssl_verification()

def cp_score(score, side):
    return score.pov(side).score(mate_score=10000)
#end of cp_score()

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
        return [ (None, 0) ]
    #end of if
    lst = get_master_moves(board)
    res = [ (parse_move_san(board, tup[0]),sum(tup[1:])) for tup in lst ]
    return res
#end of retrive_move_stats()


def load_game(inp_fn):
    gm = GameManager(inp_fn)
    return gm.games[0]
#end of load_game()


def store_game(game, out_fn):
    try:
        with open(out_fn, "w", encoding="utf-8") as pgn_file:
            exporter = chess.pgn.FileExporter(pgn_file)
            game.accept(exporter)
            return True
        #end of with
    except Exception as e:
        sys.stderr.write('Error in saving PGN file: %s\n' %(str(e)))        
        return False
    #end of try/except
    return True
#end of store_game()

def find_variation(node, move):
    if not node.variations:
        return None
    #end of if
    for next_node in node.variations:
        if next_node.move == move:
            return next_node
        #end of if
    #end of for
    return None
#end of find_variation()

def parse_move_san(board, move_san):
    try:
        move = board.parse_san(move_san)
    except ValueError:
        return None
    #end of try/except
    return move
#end of parse_move_san()

def add_game(src_node, tar_node):
    for src_var in src_node.variations:
        next_tar = find_variation(tar_node, src_var.move)
        if next_tar is None:
            # a new src mov
            next_tar = tar_node.add_variation(src_var.move)
            next_tar.comment = src_var.comment
        #end of if
        add_game(src_var, next_tar)
    #end of for src_var
#end of add_game()

def merge_games(inp_fn, out_fn):
    sys.stderr.write('loading games from file: %s\n' %(inp_fn))
    gm = GameManager(inp_fn)
    sys.stderr.write('Number of loaded games: %d\n' %(len(gm.games)))
    if not gm.games:
        return False
    root = gm.games[0]
    for game in gm.games[1:]:
        add_game(game, root)
    #end of for
    return store_game(root, out_fn)
#end of merge_games()


class k_unit:
    def __init__(self, conf):
        #self.is_my_turn = is_my_turn 
        self.stat = 0  # general game statistics 
        self.def_stat = 0  # general game statistics out of tree
        self.hist = [] # observation history
        self.belief = conf.get('prior', 0.1) # current belief, we know the move
        self.guess = conf.get('guess', 0.1) # probability to guess the move 
        #self.lr = conf.get('lrate', 0.1) # probability to learn the move after observation
        self.max_score = None # SF score for best move
        self.opt_score = None # expected recursive score, assuming all hits
        self.def_score = None # expected SF score out of tree
        self.prob = self.belief + (1.0-self.belief)*self.guess # prob. to take the move
        self.max_loss = None # current expected maximum variation loss
    #end of __init__()

    def update_prob(self):
        self.prob = self.belief + (1.0 - self.belief) * self.guess
      #end of update_prob()

    def add_observation(self, obs):
        self.hist.append(obs)
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

    def add_review(self, lrate):
        prev = self.belief
        self.belief = prev + (1.0 - prev) * lrate
        self.update_prob()
    #end of add_review()

    def get_local_loss(self, def_score):
        return (1.0 - self.prob) * max(0, self.opt_score - def_score)
    #end of get_local_loss()

    def get_prop_loss(self):
        return self.prob * self.max_loss
    #end of get_prop_loss()
    
    def to_formal_string(self):
        return '%d %d %.2f %.2f %.4f %.4f %.6f %.6f' %(self.stat, self.def_stat, self.max_score, self.def_score, self.opt_score, self.guess, self.belief, self.prob)
    #end of to_formal_string()

    def read_from_formal_string(self, buf):
        try:
            vals = buf.split(' ')
            self.stat = int(vals[0])
            self.def_stat = int(vals[1])
            self.max_score = float(vals[2])
            self.def_score = float(vals[3])
            self.opt_score = float(vals[4])
            self.guess = float(vals[5])
            self.belief = float(vals[6])
            self.prob = float(vals[7])
        except (ValueError, IndexError):
            pass
    #end of read_from_formal_string()
#end of class k_unit




class OpeningTrainer(GameNavigator):
    def __init__(self, my_side, inp_fn=None, engine_path=None):
        #self.conf = conf
        self.my_side = chess.WHITE if (my_side == 'white') else chess.BLACK
        self.engine = None
        if engine_path:
            self.engine = load_engine(engine_path)
        if inp_fn:
            if not self.load(inp_fn):
                sys.stderr.write('OpeningTrainer initialization is failed\n')
                sys.exit(1)
            #end of if
        else:
            game = chess.pgn.Game()
            game.setup(chess.Board())
            #game.comment = k_unit(self.conf)
            super().__init__(game)
        #end of if


    #end of __init__()

    def _count_nodes(self, node):
        count = 1
        for var in node.variations:
            count += self._count_nodes(var)
        return count

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
            obs = '[' + ','.join([ str(int(x)) for x in rec.hist ]) + ']'
            loss = 'None' if rec.max_loss is None else '%.6f' %(rec.max_loss)
            print('%s %s : %.2f %.2f opt: %.4f bel: %.6f loss: %s %s' %(move_san, turn, rec.max_score, rec.def_score, rec.opt_score, rec.belief, loss, obs))
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
        if buf:
            node.comment.read_from_formal_string(buf)
        for var in node.variations:
            self.dearchivate(var)
        #end of for
    #end of dearchivate()

    def store(self, out_fn):
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
        self.dearchivate()
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
        if rec.def_score is None:
            scores = [ var.comment.max_score for var in node.variations ]
            cnts = [ var.comment.stat for var in node.variations ]
        else:
            scores = [ var.comment.max_score for var in node.variations ] + [ rec.def_score] 
            cnts = [ var.comment.stat for var in node.variations ] + [ rec.def_stat ]
        #end of if/else
        score_cnts = softmax(bfact * np.array(scores))
        cmb_cnts = score_cnts + cfact * np.array(cnts)
        probs = cmb_cnts / cmb_cnts.sum()
        for i,var in enumerate(node.variations):
            var.comment.prob = probs[i]
        #end of for
        if rec.def_score is not None:
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
        rem_cnts = filter(lambda x: x[0] not in var_moves, stats)
        node.comment.def_stat = sum([x[1] for x in rem_cnts])
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
        board = node.board()
        num = len(node.variations)
        cands,depth = select_move_candidates(engine, board, 1+num)
        if not cands:
            if board.is_checkmate():
                score = -10000
            else:
                score = 0
            node.comment.max_score = score
            node.comment.def_score = None
            return

        node.comment.max_score = cp_score( cands[0][1], self.my_side)
        moves = set([ var.move for var in node.variations ])
        rem_cands =[ x for x in filter(lambda x: x[0] not in moves, cands) ]
        node.comment.def_score = cp_score(cands[0][1], self.my_side) if rem_cands else None
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
        def_score = node.comment.def_score
        probs = self.compute_var_distrib(node, conf)
        prod = (probs * np.array(scores)).sum()
        if def_score is not None:
            def_prob = 1.0 - probs.sum()
            prod = prod + def_prob * def_score 
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

    def setup_all_scores(self, conf, stat_client, node=None, progress_state=None):
        if node is None:
            node = self._root
            total_nodes = self._count_nodes(node)
            from rich.console import Console
            console = Console()
            progress_state = {'current': 0, 'total': total_nodes, 'console': console}

        for var in node.variations:
            self.setup_all_scores(conf, stat_client, var, progress_state)

        node.comment = k_unit(conf)
        self.compute_local_scores(node, self.engine)
        self.compute_stats(node, stat_client)
        self.compute_opt_score(node, conf)

        if progress_state:
            progress_state['current'] += 1
            console = progress_state['console']
            console.print(f"Calculating weights: {progress_state['current']}/{progress_state['total']} positions processed", end='\r')
            if progress_state['current'] == progress_state['total']:
                console.print()

    #end of setup_all_scores()

    def add_observation_line(self, src_node, tar_node=None):
        if tar_node is None:
            tar_node = self._root
        #end of if
        if (not tar_node.variations) or (not src_node.variations):
            return
        #end of if
        is_my_turn = (tar_node.board().turn == self.my_side)
        if is_my_turn:
            next_tar = tar_node.variations[0]
            next_src = find_variation(src_node, next_tar.move)
            if next_src is None:
                sys.stderr.write('No correct move in observation line: %s\n' %(str(next_tar.move)))
                sys.stderr.write('moves in obs. line: %s\n' % (' , '.join([ str(x.move) for x in src_node.variations])))
                return
            #end of if
            is_hit = ( len(src_node.variations)==1 )
            next_tar.comment.add_observation(is_hit)
            next_tar.comment.add_review()
            self.invalidate_max_loss_line(tar_node)
        else: # not is_my_turn
            next_src = src_node.variations[0]
            next_tar = find_variation(tar_node, next_src.move)
            if next_tar is None:
                sys.stderr.write('Unknown move in observation line: %s\n' %(str(next_src.move)))
                sys.stderr.write('Existing moves in obs. line: %s\n' % (' , '.join([ str(x.move) for x in tar_node.variations])))
                return
            #end of if
        #end of if/else
        self.add_observation_line(next_src, next_tar)
    #end of add_observation_line()

    def compute_max_loss(self, node=None):
        if node is None:
            node = self._root
        #end of if
        rec = node.comment
        is_my_turn = (node.board().turn == self.my_side)
        if rec.max_loss is not None:
            # do nothing
            return rec.max_loss
        elif not node.variations:
            rec.max_loss = 0.0
        elif is_my_turn:
            next_node = node.variations[0]
            loss = self.compute_max_loss(next_node)
            next_rec = next_node.comment
            rec.max_loss = next_rec.get_local_loss(rec.def_score) + next_rec.get_prop_loss()
        else:
            for var in node.variations:
                self.compute_max_loss(var)
            #end of for
            cands = [ var.comment.get_prop_loss() for var in node.variations ]
            rec.max_loss = np.max( cands )
        #end of if/else
        return rec.max_loss
    #end of compute_max_loss()

    def select_max_loss_move(self, node=None):
        if node is None:
            node = self._node
        #end of if
        if not node.variations:
            return None
        #end of if
        if node.comment.max_loss is None:
            node.comment.max_loss = self.compute_max_loss(node)
        #end of if
        is_my_turn = (node.board().turn == self.my_side)
        if is_my_turn:
            move = node.variations[0].move
        else:
            cands = [ var.comment.get_prop_loss() for var in node.variations ]
            i = np.argmax(cands)
            move = node.variations[i].move
        #end of if/else
        move_san = node.board().san(move)
        return move_san
    #end of select_max_loss_move()
    
    def go_root(self):
        self._node = self._root
    #end of go_root()
    
    def invalidate_max_loss_line(self, node=None):
        if node == None:
            node = self._node
        #end of if
        while node is not None:
            if node.comment.max_loss is None:
                return
            #end of if
            node.comment.max_loss = None
            node = node.parent
        #end of while
    #end of invalidate_max_loss_line()

    def review_my_move(self, lrate):
        node = self._node
        is_my_turn = (node.board().turn == self.my_side)
        if not is_my_turn:
            sys.stderr.write('Error: It is not your move\n')
            return None
        #end of if
        if not node.variations:
            sys.stderr.write('Error: No next move is defined\n')
            return None
        #end of if
        self.invalidate_max_loss_line(node)
        self.make_move('')
        move = self._node.move
        self._node.comment.add_review(lrate)
        move_san = node.board().san(move)
        return move_san
    #end of review_my_move()

    def try_my_move(self, move_san):
        node = self._node
        is_my_turn = (node.board().turn == self.my_side)
        if not is_my_turn:
            sys.stderr.write('Error: It is not your move\n')
            return False
        #end of if
        if not node.variations:
            sys.stderr.write('Error: No next move is defined\n')
            return False
        #end of if
        next_node = node.variations[0]
        if not move_san:
            user_move = None
        else:
            user_move = parse_move_san(node.board(), move_san)
            if user_move is None:
                sys.stderr.write('Error: Illegal move: %s\n' %(move_san))
                return False
            #end of if
        #end of if/else
        true_move = next_node.move
        obs = (user_move == true_move)
        next_node.comment.add_observation(obs)
        self.invalidate_max_loss_line(node)
        return obs
    #end of try_my_move()

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


#end of OpeningTrainer class

if __name__=='__main__':
    argc = len(sys.argv)
    my_side = sys.argv[1]
    pgn_fn = sys.argv[2]
    engine_path = sys.argv[3] if argc > 3 else None
    stat_client = sys.argv[4] if argc >4 else None

    if not(my_side in ['white', 'black']):
        out_fn = my_side
        print('Calling to merge_games()')
        res = merge_games(pgn_fn, out_fn)
        print('res=%s' %(str(res)))
        sys.exit(0)
    #end of if

    conf = {'lrate':0.1}

    engine = load_engine(engine_path) if engine_path else None

    trainer = OpeningTrainer( my_side, pgn_fn)
    if engine is None:
        print('Calling to dearchivate()')
        trainer.dearchivate()
    else:
        disable_ssl_verification()
        print('calling to setup_all_scores()')
        trainer.setup_all_scores(conf, engine, stat_client)
    #end of if/else
    print('loaded lines:')
    trainer.print_all_lines()
    print('------------')
    val = trainer.compute_max_loss()
    trainer.store('start.pgn')
    print('max_loss: %f' %(val))
    for i in range(10):
        if trainer.is_at_eol():
            sys.stderr.write('EOL is reached\n')
            break
        #end of if
        if trainer.is_my_turn():
            res = trainer.try_my_move('')
            print('try_my_move("") -> %s' %(str(res)))
            move_san = trainer.review_my_move(conf.get('lrate'))
            print('review_my move() -> %s' %(str(move_san)))
        else:
            move_san = trainer.select_max_loss_move()
            if move_san is None:
                print('EOL is reached')
                break
            #end of if
            print('max_loss move: %s' %(str(move_san)))
            res = trainer.go_forward(move_san)
            if not res:
                sys.stderr.write('go_forward() is Failed with move: %s\n' %(str(move_san)))
                break
            #end of if
        #end of if/else
    #end of for
    trainer.store('step1.pgn')
    val = trainer.compute_max_loss()
    print('max_loss: %f' %(val))
    #trainer.print_all_scores()
#end of if
