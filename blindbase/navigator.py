from __future__ import annotations

import io
import re
from typing import List

import chess
import chess.pgn


__all__ = ["GameNavigator"]


class GameNavigator:
    """Wrap a *chess.pgn.Game* with navigation helpers.

    This code is lifted unchanged from the original monolith so the CLI can be
    refactored gradually.
    """

    def __init__(self, game: chess.pgn.Game):
        self.original_game = game
        self.working_game = chess.pgn.Game()
        self.copy_headers(game, self.working_game)
        temp_board = chess.Board()
        if game.headers.get("FEN"):
            try:
                temp_board.set_fen(game.headers["FEN"])
                self.working_game.setup(temp_board)
            except ValueError:
                print("Warning: Invalid FEN. Using standard position.")
                self.working_game.setup(chess.Board())
        else:
            self.working_game.setup(chess.Board())
        if game.variations:
            self.copy_moves(game, self.working_game)
        self.current_node: chess.pgn.ChildNode = self.working_game  # type: ignore[assignment]
        self.move_history: List[chess.Move] = []
        self.has_changes = False

    # ------------------------------------------------------------------
    # Internal helpers (verbatim)
    # ------------------------------------------------------------------

    def copy_headers(self, source: chess.pgn.Game, target: chess.pgn.Game):
        for key, value in source.headers.items():
            target.headers[key] = value

    def copy_moves(self, source_node_start, target_node_start):
        if not source_node_start.variations:
            return
        q = [(source_node_start, target_node_start)]
        visited_source_nodes = set()
        while q:
            current_source_parent, current_target_parent = q.pop(0)
            if current_source_parent in visited_source_nodes:
                continue
            visited_source_nodes.add(current_source_parent)
            if current_source_parent.variations:
                main_src_variation_node = current_source_parent.variations[0]
                new_tgt_node = current_target_parent.add_variation(main_src_variation_node.move)
                if main_src_variation_node.comment:
                    new_tgt_node.comment = main_src_variation_node.comment
                q.append((main_src_variation_node, new_tgt_node))
                for i in range(1, len(current_source_parent.variations)):
                    src_sideline_node = current_source_parent.variations[i]
                    new_sideline_tgt_node = current_target_parent.add_variation(src_sideline_node.move)
                    if src_sideline_node.comment:
                        new_sideline_tgt_node.comment = src_sideline_node.comment
                    q.append((src_sideline_node, new_sideline_tgt_node))

    # ------------------------------------------------------------------
    # Public API (verbatim)
    # ------------------------------------------------------------------

    def get_current_board(self) -> chess.Board:
        board = self.working_game.board()
        path_to_current = []
        node = self.current_node
        while node.parent is not None:
            path_to_current.append(node.move)
            node = node.parent
        path_to_current.reverse()
        for move in path_to_current:
            board.push(move)
        return board

    def show_variations(self):
        if not self.current_node.variations:
            return []
        board_at_current_node = self.get_current_board()
        variations_list = []
        for i, variation_node in enumerate(self.current_node.variations):
            try:
                san_move = board_at_current_node.san(variation_node.move)
            except ValueError:
                san_move = variation_node.move.uci() + " (raw UCI)"
            except AssertionError:
                san_move = variation_node.move.uci() + " (raw UCI, SAN assertion)"
            comment = f" ({variation_node.comment})" if variation_node.comment else ""
            variations_list.append(f"{i+1}. {san_move}{comment}")
        return variations_list

    def make_move(self, move_input):
        board = self.get_current_board()
        if not move_input.strip():
            if self.current_node.variations:
                chosen_variation_node = self.current_node.variations[0]
                self.current_node = chosen_variation_node
                return True, chosen_variation_node.move
            return False, None
        try:
            var_num = int(move_input) - 1
            if 0 <= var_num < len(self.current_node.variations):
                chosen_variation_node = self.current_node.variations[var_num]
                self.current_node = chosen_variation_node
                return True, chosen_variation_node.move
        except ValueError:
            pass
        parsed_move = None
        try:
            parsed_move = board.parse_san(move_input)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            try:
                parsed_move = board.parse_uci(move_input)
            except (chess.InvalidMoveError, chess.IllegalMoveError):
                pass
        if parsed_move and parsed_move in board.legal_moves:
            for variation_node in self.current_node.variations:
                if variation_node.move == parsed_move:
                    self.current_node = variation_node
                    return True, parsed_move
            new_node = self.current_node.add_variation(parsed_move)
            self.current_node = new_node
            self.has_changes = True
            return True, parsed_move
        return False, None

    def go_back(self):
        if self.current_node.parent is None:
            return False
        self.current_node = self.current_node.parent
        return True

    def delete_variation(self, var_num_1_indexed):
        if not self.current_node.variations:
            return False, "No variations to delete."
        if not (1 <= var_num_1_indexed <= len(self.current_node.variations)):
            return False, f"Invalid variation number. Must be 1-{len(self.current_node.variations)}."
        variation_to_remove = self.current_node.variations[var_num_1_indexed - 1]
        self.current_node.remove_variation(variation_to_remove.move)
        self.has_changes = True
        return True, f"Variation {var_num_1_indexed} ('{variation_to_remove.move.uci()}') deleted."

    def get_pgn_string(self) -> str:
        pgn_exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return self.working_game.accept(pgn_exporter)

    def get_current_path(self):
        path = []
        node = self.current_node
        while node.parent is not None:
            path.append(node.move)
            node = node.parent
        path.reverse()
        return path

    def update_from_broadcast_pgn(self, pgn_string, game_identifier):
        pgn_io = io.StringIO(pgn_string)
        game = chess.pgn.read_game(pgn_io)
        if (
            game
            and game.headers.get("White") == game_identifier[0]
            and game.headers.get("Black") == game_identifier[1]
        ):
            current_path = self.get_current_path()
            self.working_game = game
            new_node = self.working_game
            for move in current_path:
                found = False
                for variation in new_node.variations:
                    if variation.move == move:
                        new_node = variation
                        found = True
                        break
                if not found:
                    new_node = self.working_game
                    while new_node.variations:
                        new_node = new_node.variations[0]
                    break
            self.current_node = new_node

    def get_clocks(self):
        last_white_comment = ""
        last_black_comment = ""
        current = self.current_node
        while current.parent is not None:
            if current.ply() % 2 == 1:
                if current.comment:
                    last_white_comment = current.comment
            else:
                if current.comment:
                    last_black_comment = current.comment
            current = current.parent
        # Extract latest clock comments, updating only the side that just moved.
        clk_pattern = r"\[%clk\s+(\d+:\d{2}:\d{2})\]"
        white_time = "-"
        black_time = "-"
        node = self.current_node  # start at the last played move
        while node is not None:
            comment = node.comment or ""
            m = re.search(clk_pattern, comment)
            if m:
                t_val = m.group(1)
                side = chess.WHITE if node.ply() % 2 == 1 else chess.BLACK
                if side == chess.WHITE and white_time == "-":
                    white_time = t_val
                elif side == chess.BLACK and black_time == "-":
                    black_time = t_val
                if white_time != "-" and black_time != "-":
                    break
            node = node.parent
        return white_time, black_time