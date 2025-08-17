import sys
import chess

from blindbase.core.pgn import GameManager

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
    root = gm.games[0]
    for game in gm.games[1:]:
        add_game(game, root)
    #end of for
    return store_game(root, out_fn)
#end of merge_games()

if __name__ == '__main__':
    argc = len(sys.argv)
    inp_fn = sys.argv[1]
    out_fn = sys.argv[2]

    merge_games(inp_fn, out_fn)
#end of if
