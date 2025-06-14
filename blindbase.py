import chess
import chess.pgn
import chess.engine
import requests
from urllib.parse import quote
import time
import sys
import threading
import shutil
import io
from datetime import datetime
import os
import json
import queue
import re

# Global variables
settings_manager = None
UI_SCREEN_BUFFER_HEIGHT = 35

def clear_screen_and_prepare_for_new_content(is_first_draw=False):
    if is_first_draw:
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
        return
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')
    sys.stdout.flush()

class SettingsManager:
    def __init__(self, settings_filename="settings.json"):
        self.settings_filename = settings_filename
        self.default_settings = {
            "lichess_moves_count": 5,
            "engine_lines_count": 3,
            "show_chessboard": True,
            "analysis_block_padding": 3,
            "engine_path": "./stockfish",
            "pgn_file_directory": ".",
            "default_pgn_filename": "games.pgn",
            "games_per_page": 10
        }
        self.settings = {}
        self.load_settings()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_filename):
                with open(self.settings_filename, 'r') as f:
                    loaded_settings = json.load(f)
                    self.settings = self.default_settings.copy()
                    self.settings.update(loaded_settings)
                    for key, value in self.default_settings.items():
                        if key not in self.settings:
                            self.settings[key] = value
                        else:
                            if isinstance(value, int): self.settings[key] = int(self.settings.get(key, value))
                            elif isinstance(value, bool): self.settings[key] = bool(self.settings.get(key, value))
                            else: self.settings[key] = str(self.settings.get(key, value))
            else:
                self.settings = self.default_settings.copy()
                self.save_settings()
        except (json.JSONDecodeError, IOError, TypeError, ValueError) as e:
            print(f"Warning: Error loading settings file '{self.settings_filename}': {e}. Using defaults.")
            self.settings = self.default_settings.copy()
            self.save_settings()

    def save_settings(self):
        try:
            pgn_dir = self.settings.get("pgn_file_directory", self.default_settings["pgn_file_directory"])
            if pgn_dir == ".": pgn_dir = os.getcwd()
            os.makedirs(pgn_dir, exist_ok=True)
            with open(self.settings_filename, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except IOError as e:
            print(f"Error saving settings to '{self.settings_filename}': {e}")

    def get(self, key):
        return self.settings.get(key, self.default_settings.get(key))

    def set(self, key, value):
        if key in self.default_settings:
            default_value = self.default_settings[key]
            if isinstance(default_value, int): value = int(value)
            elif isinstance(default_value, bool): value = bool(value)
        self.settings[key] = value
        self.save_settings()

class GameManager:
    def __init__(self, pgn_filename):
        self.pgn_filename = pgn_filename
        self.games = []
        self.current_game_index = 0
        self.load_games()

    def load_games(self):
        self.games = []
        pgn_dir = os.path.dirname(self.pgn_filename)
        if pgn_dir:
            os.makedirs(pgn_dir, exist_ok=True)
        if not os.path.exists(self.pgn_filename):
            print(f"PGN file {self.pgn_filename} not found. Creating new.")
            try:
                with open(self.pgn_filename, 'w', encoding='utf-8') as pgn_file:
                    pass
            except IOError as e:
                print(f"Error creating PGN file '{self.pgn_filename}': {e}")
                return
        else:
            print(f"Loading games from {self.pgn_filename}...")
        try:
            with open(self.pgn_filename, 'r', encoding='utf-8') as pgn_file:
                while True:
                    offset = pgn_file.tell()
                    try:
                        game = chess.pgn.read_game(pgn_file)
                    except Exception as e:
                        line = pgn_file.readline()
                        while line and not line.startswith("[Event "):
                            line = pgn_file.readline()
                        if line:
                            pgn_file.seek(pgn_file.tell() - len(line.encode('utf-8')))
                            continue
                        else:
                            break
                    if game is None:
                        break
                    self.games.append(game)
            print(f"Loaded {len(self.games)} games from {self.pgn_filename}")
            if not self.games:
                self.current_game_index = 0
            elif self.current_game_index >= len(self.games):
                self.current_game_index = len(self.games) - 1
        except Exception as e:
            print(f"Error loading PGN file: {e}")
            self.games = []
            self.current_game_index = 0

    def save_games(self):
        try:
            backup_filename = self.pgn_filename + ".backup"
            if os.path.exists(self.pgn_filename):
                shutil.copy2(self.pgn_filename, backup_filename)
            with open(self.pgn_filename, 'w', encoding='utf-8') as pgn_file:
                for game in self.games:
                    exporter = chess.pgn.FileExporter(pgn_file)
                    game.accept(exporter)
            print(f"Games saved to {self.pgn_filename}")
            return True
        except Exception as e:
            print(f"Error saving PGN file: {e}")
            return False

    def add_new_game(self):
        clear_screen_and_prepare_for_new_content()
        print("--- Add New Game ---")
        white_name = input("White player name (default: Unknown): ").strip() or "Unknown"
        black_name = input("Black player name (default: Unknown): ").strip() or "Unknown"
        white_elo = input("White ELO (optional): ").strip()
        black_elo = input("Black ELO (optional): ").strip()
        result = input("Result (1-0, 0-1, 1/2-1/2, * default): ").strip()
        if result not in ["1-0", "0-1", "1/2-1/2", "*"]:
            result = "*"
        event = input("Event (optional): ").strip()
        site = input("Site (optional): ").strip()
        date = input(f"Date (YYYY.MM.DD, Enter for {datetime.now().strftime('%Y.%m.%d')}): ").strip() or datetime.now().strftime("%Y.%m.%d")
        round_num = input("Round (optional): ").strip()
        game = chess.pgn.Game()
        game.headers["White"] = white_name
        game.headers["Black"] = black_name
        game.headers["Result"] = result
        game.headers["Date"] = date
        if white_elo.isdigit(): game.headers["WhiteElo"] = white_elo
        if black_elo.isdigit(): game.headers["BlackElo"] = black_elo
        if event: game.headers["Event"] = event
        if site: game.headers["Site"] = site
        if round_num: game.headers["Round"] = round_num
        self.games.append(game)
        self.current_game_index = len(self.games) - 1
        print(f"\nNew game added! Total games: {len(self.games)}")
        input("Press Enter to continue...")
        return True

class BroadcastManager:
    def __init__(self):
        self.broadcasts = []
        self.selected_broadcast = None
        self.selected_round = None
        self.selected_game = None

    def fetch_broadcasts(self):
        url = "https://lichess.org/api/broadcast"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                print(f"Response text: {response.text}")
                self.broadcasts = []
                return False
            self.broadcasts = data.get('official', [])
            return True
        except Exception as e:
            print(f"Error fetching broadcasts: {e}")
            self.broadcasts = []
            return False

    def fetch_rounds(self, broadcast):
        return broadcast.get('rounds', [])

    def fetch_games(self, round_id):
        url = f"https://lichess.org/api/broadcast/{round_id}.pgn"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            pgn_text = response.text
            games = []
            pgn_io = io.StringIO(pgn_text)
            while True:
                game = chess.pgn.read_game(pgn_io)
                if game is None:
                    break
                site = game.headers.get('Site', '')
                game_id_match = re.search(r'https://lichess.org/(\w+)', site)
                if game_id_match:
                    game_id = game_id_match.group(1)
                    game.game_id = game_id  # Attach game_id to the game object
                games.append(game)
            return games
        except Exception as e:
            print(f"Error fetching games: {e}")
            return []

class GameNavigator:
    def __init__(self, game):
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
        self.current_node = self.working_game
        self.move_history = []
        self.has_changes = False

    def copy_headers(self, source, target):
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

    def get_current_board(self):
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

    def get_pgn_string(self):
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
        if game and game.headers.get('White') == game_identifier[0] and game.headers.get('Black') == game_identifier[1]:
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
        clk_pattern = r"\{\[%clk (\d+:\d+:\d+)\]\}"
        white_clk = re.search(clk_pattern, last_white_comment)
        black_clk = re.search(clk_pattern, last_black_comment)
        white_time = white_clk.group(1) if white_clk else "N/A"
        black_time = black_clk.group(1) if black_clk else "N/A"
        return white_time, black_time

def get_analysis_block_height(current_settings_manager):
    num_engine_lines = current_settings_manager.get("engine_lines_count")
    padding = current_settings_manager.get("analysis_block_padding")
    return 1 + num_engine_lines + padding

def clear_analysis_block_dynamic(current_settings_manager):
    block_height = get_analysis_block_height(current_settings_manager)
    sys.stdout.write(f"\033[{block_height}A")
    for _ in range(block_height):
        sys.stdout.write("\033[2K\n")
    sys.stdout.write(f"\033[{block_height}A")
    sys.stdout.flush()

def print_analysis_refined(depth, lines_data, current_settings_manager):
    num_engine_display_lines = current_settings_manager.get("engine_lines_count")
    block_height = get_analysis_block_height(current_settings_manager)
    try:
        terminal_width = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        terminal_width = 80
    sys.stdout.write(f"\033[{block_height}A")
    depth_text = f"Depth: {depth}"
    sys.stdout.write("\033[2K" + depth_text[:terminal_width] + "\n")
    for i in range(num_engine_display_lines):
        line_prefix = f"Line {i + 1}: "
        content = lines_data[i] if i < len(lines_data) and lines_data[i] else "..."
        full_line_text = line_prefix + content
        line_to_print = (full_line_text[:terminal_width - 3] + "...") if len(full_line_text) > terminal_width else full_line_text
        sys.stdout.write("\033[2K" + line_to_print + "\n")
    remaining_lines_to_fill = block_height - (1 + num_engine_display_lines)
    for _ in range(remaining_lines_to_fill):
        sys.stdout.write("\033[2K\n")
    sys.stdout.flush()

def analysis_thread_refined(engine, board, stop_event, current_settings_manager):
    num_engine_lines = current_settings_manager.get("engine_lines_count")
    displayed_depth = 0
    displayed_lines_content = ["..."] * num_engine_lines
    latest_data_at_max_depth = {i: "" for i in range(1, num_engine_lines + 1)}
    max_depth_from_engine_info = 0
    last_display_update_time = time.time()
    print_analysis_refined(displayed_depth, displayed_lines_content, current_settings_manager)
    try:
        with engine.analysis(board, multipv=num_engine_lines, limit=chess.engine.Limit(depth=None)) as analysis:
            for info in analysis:
                if stop_event.is_set():
                    break
                info_depth = info.get("depth")
                multipv_num = info.get("multipv")
                pv = info.get("pv")
                score = info.get("score")
                if info_depth is not None:
                    if info_depth > max_depth_from_engine_info:
                        max_depth_from_engine_info = info_depth
                        latest_data_at_max_depth = {i: "" for i in range(1, num_engine_lines + 1)}
                    elif info_depth < max_depth_from_engine_info:
                        continue
                else:
                    if not all([multipv_num is not None, pv, score is not None]):
                        continue
                if info_depth == max_depth_from_engine_info:
                    if not all([multipv_num is not None, pv, score is not None]):
                        continue
                    pv_san = "..."
                    try:
                        temp_board = board.copy()
                        pv_san = temp_board.variation_san(pv)
                    except Exception:
                        if pv:
                            pv_san = " ".join([board.uci(m) for m in pv]) + " (UCI)"
                        else:
                            pv_san = "Error in PV"
                    if score.is_mate():
                        mate_in_plies = score.pov(board.turn).mate()
                        evaluation = f"M{abs(mate_in_plies)}" if mate_in_plies is not None else "Mate"
                    else:
                        cp_score = score.pov(board.turn).score(mate_score=10000)
                        evaluation = f"{cp_score / 100:.2f}" if cp_score is not None else "N/A"
                    latest_data_at_max_depth[multipv_num] = f"{evaluation} {pv_san}"
                should_update_display_flag = False
                new_depth_to_show = displayed_depth
                potential_new_lines = list(displayed_lines_content)
                if max_depth_from_engine_info > displayed_depth:
                    if latest_data_at_max_depth.get(1):
                        new_depth_to_show = max_depth_from_engine_info
                        for i in range(1, num_engine_lines + 1):
                            if latest_data_at_max_depth.get(i):
                                potential_new_lines[i-1] = latest_data_at_max_depth[i]
                        if potential_new_lines != displayed_lines_content or new_depth_to_show != displayed_depth:
                            should_update_display_flag = True
                elif max_depth_from_engine_info == displayed_depth:
                    changed_at_current_depth = False
                    for i in range(1, num_engine_lines + 1):
                        if latest_data_at_max_depth.get(i) and latest_data_at_max_depth[i] != potential_new_lines[i-1]:
                            potential_new_lines[i-1] = latest_data_at_max_depth[i]
                            changed_at_current_depth = True
                    if changed_at_current_depth:
                        should_update_display_flag = True
                if should_update_display_flag:
                    new_lines_to_show = potential_new_lines
                    current_time = time.time()
                    if current_time - last_display_update_time > 0.15:
                        print_analysis_refined(new_depth_to_show, new_lines_to_show, current_settings_manager)
                        displayed_depth = new_depth_to_show
                        displayed_lines_content = new_lines_to_show[:]
                        last_display_update_time = current_time
                time.sleep(0.01)
    except chess.engine.EngineTerminatedError:
        clear_analysis_block_dynamic(current_settings_manager)
        sys.stdout.write("\033[2KEngine terminated unexpectedly.\n")
        for _ in range(get_analysis_block_height(current_settings_manager) - 1): sys.stdout.write("\033[2K\n")
        sys.stdout.flush()
    except Exception as e:
        clear_analysis_block_dynamic(current_settings_manager)
        error_message = f"Analysis thread error: {str(e)[:80]}"
        sys.stdout.write(f"\033[2K{error_message}\n")
        for _ in range(get_analysis_block_height(current_settings_manager) - 1): sys.stdout.write("\033[2K\n")
        sys.stdout.flush()

def read_board_aloud(board):
    clear_screen_and_prepare_for_new_content()
    print("--- BOARD READING ---")
    piece_order_map = { chess.KING: 0, chess.QUEEN: 1, chess.ROOK: 2, chess.BISHOP: 3, chess.KNIGHT: 4, chess.PAWN: 5 }
    piece_chars = { chess.PAWN: '', chess.ROOK: 'R', chess.KNIGHT: 'N', chess.BISHOP: 'B', chess.QUEEN: 'Q', chess.KING: 'K' }
    pieces_data = []
    for sq_idx in chess.SQUARES:
        pc = board.piece_at(sq_idx)
        if pc:
            sq_name = chess.square_name(sq_idx)
            disp_str = (piece_chars[pc.piece_type] + sq_name) if pc.piece_type != chess.PAWN else sq_name
            pieces_data.append({'display': disp_str, 'color': pc.color, 'type': pc.piece_type, 'file': chess.square_file(sq_idx), 'rank': chess.square_rank(sq_idx)})
    sort_key = lambda p: (piece_order_map[p['type']], p['file'], p['rank'])
    wp = [p['display'] for p in sorted([pd for pd in pieces_data if pd['color'] == chess.WHITE], key=sort_key)]
    bp = [p['display'] for p in sorted([pd for pd in pieces_data if pd['color'] == chess.BLACK], key=sort_key)]
    print("White Pieces:")
    if wp: [print(f"  {p_str}") for p_str in wp]
    else: print("  None")
    print("\nBlack Pieces:")
    if bp: [print(f"  {p_str}") for p_str in bp]
    else: print("  None")
    print("-" * 20)
    input("Press Enter to continue...")

def get_lichess_data(board, current_settings_manager):
    fen = board.fen()
    fen_enc = quote(fen)
    url = f"https://explorer.lichess.ovh/masters?fen={fen_enc}"
    num_moves = current_settings_manager.get("lichess_moves_count")
    if num_moves == 0: return
    print("\n--- Lichess Masters Database ---")
    try:
        resp = requests.get(url, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        op_name = "N/A"
        op_info = data.get("opening")
        if op_info: op_name = op_info.get("name", "N/A")
        if op_name != "N/A": print(f"Opening: {op_name}")
        moves = data.get("moves", [])
        if moves:
            print(f"Top {min(num_moves, len(moves))} moves:")
            for m_data in moves[:num_moves]:
                tot = m_data["white"] + m_data["draws"] + m_data["black"]
                if tot > 0:
                    wp, dp, bp = (m_data["white"]/tot)*100, (m_data["draws"]/tot)*100, (m_data["black"]/tot)*100
                    print(f"  {m_data['san']}: {tot} games (W:{wp:.0f}%, D:{dp:.0f}%, B:{bp:.0f}%)")
        else:
            print("No Lichess Masters data for this position.")
    except requests.exceptions.Timeout:
        print("Lichess Masters: Request timed out.")
    except requests.exceptions.RequestException as e:
        print(f"Lichess Masters: Error - {e}")
    except Exception as e:
        print(f"Lichess Masters: Processing error - {e}")

def show_settings_menu(current_settings_manager):
    while True:
        clear_screen_and_prepare_for_new_content()
        print("--- SETTINGS MENU ---")
        print(f"1. Lichess Moves Count (current: {current_settings_manager.get('lichess_moves_count')})")
        print(f"2. Engine Analysis Lines (current: {current_settings_manager.get('engine_lines_count')})")
        print(f"3. Show Chessboard (current: {'Yes' if current_settings_manager.get('show_chessboard') else 'No'})")
        print(f"4. Analysis Block Padding (current: {current_settings_manager.get('analysis_block_padding')})")
        print(f"5. Engine Path (current: {current_settings_manager.get('engine_path')})")
        print(f"6. PGN File Directory (current: {current_settings_manager.get('pgn_file_directory')})")
        print(f"7. Default PGN Filename (current: {current_settings_manager.get('default_pgn_filename')})")
        print(f"8. Games Per Page in Menu (current: {current_settings_manager.get('games_per_page')})")
        print("9. Back to Game Selection")
        choice = input("\nSelect option: ").strip()
        if choice == '1':
            try:
                val = int(input(f"New Lichess moves count (0-10, current {current_settings_manager.get('lichess_moves_count')}): "))
                current_settings_manager.set("lichess_moves_count", max(0, min(10, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == '2':
            try:
                val = int(input(f"New engine lines count (1-10, current {current_settings_manager.get('engine_lines_count')}): "))
                current_settings_manager.set("engine_lines_count", max(1, min(10, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == '3':
            current_settings_manager.set("show_chessboard", not current_settings_manager.get("show_chessboard"))
        elif choice == '4':
            try:
                val = int(input(f"New analysis padding lines (0-5, current {current_settings_manager.get('analysis_block_padding')}): "))
                current_settings_manager.set("analysis_block_padding", max(0, min(5, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == '5':
            val = input(f"New engine path (current {current_settings_manager.get('engine_path')}): ").strip()
            if val: current_settings_manager.set("engine_path", val)
        elif choice == '6':
            val = input(f"New PGN file directory (current {current_settings_manager.get('pgn_file_directory')}): ").strip()
            if val: current_settings_manager.set("pgn_file_directory", val)
        elif choice == '7':
            val = input(f"New default PGN filename (current {current_settings_manager.get('default_pgn_filename')}): ").strip()
            if val: current_settings_manager.set("default_pgn_filename", val)
        elif choice == '8':
            try:
                val = int(input(f"New games per page (5-50, current {current_settings_manager.get('games_per_page')}): "))
                current_settings_manager.set("games_per_page", max(5, min(50, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == '9':
            break
        else:
            print("Invalid option.")
        if choice in [str(i) for i in range(1, 9)]:
            print("Setting updated.")
            time.sleep(0.7)

current_games_page = 0

def show_game_selection_menu(game_manager, current_settings_manager):
    global current_games_page
    is_first_call_of_session = True
    games_per_page = current_settings_manager.get("games_per_page")
    menu_content_height = 5 + games_per_page
    total_menu_height = menu_content_height + 2
    while True:
        if is_first_call_of_session:
            clear_screen_and_prepare_for_new_content(is_first_draw=True)
        else:
            sys.stdout.write(f"\033[{total_menu_height}A")
            sys.stdout.flush()
        is_first_call_of_session = False
        print("\033[2K--- GAME SELECTION MENU ---")
        if not game_manager.games:
            print("\033[2KNo games loaded.")
            print("\033[2KCurrent selection: N/A")
            print("\033[2K--------------------")
            for _ in range(games_per_page):
                print("\033[2K")
            print("\033[2KCommands: 'n' (new game), 'r' (reload PGN), 's' (settings), 'b' (broadcasts), 'q' (quit)")
        else:
            total_games = len(game_manager.games)
            total_pages = (total_games + games_per_page - 1) // games_per_page
            current_games_page = max(0, min(current_games_page, total_pages - 1))
            start_index = current_games_page * games_per_page
            end_index = min(start_index + games_per_page, total_games)
            print(f"\033[2KTotal games: {total_games}. Displaying {start_index+1}-{end_index} (Page {current_games_page+1} of {total_pages})")
            print(f"\033[2KCurrent selection: {game_manager.current_game_index + 1 if game_manager.games else 'N/A'}")
            print("\033[2K--------------------")
            for i in range(start_index, start_index + games_per_page):
                if i < total_games:
                    game = game_manager.games[i]
                    marker = ">>> " if i == game_manager.current_game_index else "    "
                    white = game.headers.get("White", "N/A")[:15]
                    black = game.headers.get("Black", "N/A")[:15]
                    result = game.headers.get("Result", "*")
                    date = game.headers.get("Date", "N/A")
                    event_short = game.headers.get("Event", "")[:20]
                    event_str = f" ({event_short})" if event_short else ""
                    print(f"\033[2K{marker}{i+1:3d}. {white} vs {black} [{result}] {date}{event_str}")
                else:
                    print("\033[2K")
            cmd_list = ["<num> (view)", "'n'(new)", "'s'(set)", "'r'(reload)", "'b'(broadcasts)"]
            if total_pages > 1:
                if current_games_page > 0: cmd_list.append("'p'(prev page)")
                if current_games_page < total_pages - 1: cmd_list.append("'f'(next page)")
            cmd_list.extend(["'d <num>'(del)", "'q'(quit)"])
            print(f"\033[2KCmds: {', '.join(cmd_list)}")
        print("\033[2KCommand: ", end="", flush=True)
        choice = input().strip().lower()
        cmd_parts = choice.split()
        action = cmd_parts[0] if cmd_parts else ""
        if action == 'q':
            return None
        elif action == 'n':
            if game_manager.add_new_game():
                if game_manager.save_games(): print("\033[2KNew game added and PGN saved.")
                else: print("\033[2KNew game added, but error saving PGN.")
                return game_manager.current_game_index
        elif action == 's':
            show_settings_menu(current_settings_manager)
            is_first_call_of_session = True
        elif action == 'r':
            game_manager.load_games()
            print("\033[2KPGN file reloaded.")
            time.sleep(1)
        elif action == 'b':
            broadcast_manager = BroadcastManager()
            if broadcast_manager.fetch_broadcasts():
                selected_game = show_broadcasts_menu(broadcast_manager)
                if selected_game:
                    navigator = GameNavigator(selected_game)
                    play_game(None, engine, navigator, current_settings_manager, is_broadcast=True, 
                            broadcast_id=broadcast_manager.selected_broadcast['id'],
                            round_id=broadcast_manager.selected_round['id'],
                            game_id=selected_game.game_id,
                            game_identifier=(selected_game.headers['White'], selected_game.headers['Black']))
            is_first_call_of_session = True
        elif action == 'f' or action == 'next':
            if total_pages > 1 and current_games_page < total_pages - 1:
                current_games_page += 1
            else:
                print("\033[2KAlready on the last page or no multiple pages.")
                time.sleep(0.5)
        elif action == 'p' or action == 'prev':
            if total_pages > 1 and current_games_page > 0:
                current_games_page -= 1
            else:
                print("\033[2KAlready on the first page or no multiple pages.")
                time.sleep(0.5)
        elif action == 'd' and len(cmd_parts) > 1 and cmd_parts[1].isdigit():
            if not game_manager.games:
                print("\033[2KNo games to delete.")
                time.sleep(1)
                continue
            game_num_to_delete_1_indexed = int(cmd_parts[1])
            game_num_to_delete_0_indexed = game_num_to_delete_1_indexed - 1
            if 0 <= game_num_to_delete_0_indexed < len(game_manager.games):
                game_desc = f"{game_manager.games[game_num_to_delete_0_indexed].headers.get('White','?')} vs {game_manager.games[game_num_to_delete_0_indexed].headers.get('Black','?')}"
                confirm = input(f"\033[2KDelete game {game_num_to_delete_1_indexed} ({game_desc})? (y/N): ").lower()
                if confirm == 'y':
                    del game_manager.games[game_num_to_delete_0_indexed]
                    print("\033[2KGame deleted.")
                    if game_manager.current_game_index > game_num_to_delete_0_indexed:
                        game_manager.current_game_index -= 1
                    elif game_manager.current_game_index == game_num_to_delete_0_indexed and game_manager.current_game_index >= len(game_manager.games):
                        game_manager.current_game_index = max(0, len(game_manager.games) - 1 if game_manager.games else 0)
                    if game_manager.save_games():
                        print("\033[2KPGN file updated.")
                    else:
                        print("\033[2KError updating PGN file after deletion.")
                    time.sleep(1)
            else:
                print("\033[2KInvalid game number for deletion.")
                time.sleep(1)
        elif action.isdigit():
            if not game_manager.games:
                print("\033[2KNo games to view.")
                time.sleep(1)
                continue
            game_num_to_view_1_indexed = int(action)
            game_num_to_view_0_indexed = game_num_to_view_1_indexed - 1
            if 0 <= game_num_to_view_0_indexed < len(game_manager.games):
                game_manager.current_game_index = game_num_to_view_0_indexed
                return game_num_to_view_0_indexed
            else:
                print("\033[2KInvalid game number.")
                time.sleep(1)
        else:
            if choice:
                print("\033[2KInvalid command. Please try again.")
                time.sleep(0.5)

def show_broadcasts_menu(broadcast_manager):
    while True:
        clear_screen_and_prepare_for_new_content()
        print("--- BROADCASTS MENU ---")
        if not broadcast_manager.broadcasts:
            print("No broadcasts available.")
        else:
            for i, broadcast in enumerate(broadcast_manager.broadcasts):
                name = broadcast.get('name', 'Unknown')
                start_date = broadcast.get('startDate', 'Unknown')
                print(f"{i+1}. {name} (Start: {start_date})")
        print("\nCommands: <number> (select broadcast), 'r' (refresh), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == 'b':
            return None
        elif choice.lower() == 'r':
            broadcast_manager.fetch_broadcasts()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(broadcast_manager.broadcasts):
                broadcast_manager.selected_broadcast = broadcast_manager.broadcasts[idx]
                return show_rounds_menu(broadcast_manager)
        else:
            print("Invalid option.")

def show_rounds_menu(broadcast_manager):
    rounds = broadcast_manager.fetch_rounds(broadcast_manager.selected_broadcast)
    while True:
        clear_screen_and_prepare_for_new_content()
        print(f"--- ROUNDS for {broadcast_manager.selected_broadcast['name']} ---")
        if not rounds:
            print("No rounds available.")
        else:
            for i, round in enumerate(rounds):
                name = round.get('name', 'Unknown')
                start_date = round.get('startDate', 'Unknown')
                print(f"{i+1}. {name} (Start: {start_date})")
        print("\nCommands: <number> (select round), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == 'b':
            return None
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(rounds):
                broadcast_manager.selected_round = rounds[idx]
                return show_games_menu(broadcast_manager)
        else:
            print("Invalid option.")

def show_games_menu(broadcast_manager):
    games = broadcast_manager.fetch_games(broadcast_manager.selected_round['id'])
    while True:
        clear_screen_and_prepare_for_new_content()
        print(f"--- GAMES for {broadcast_manager.selected_round['name']} ---")
        if not games:
            print("No games available.")
        else:
            for i, game in enumerate(games):
                white = game.headers.get('White', 'Unknown')
                black = game.headers.get('Black', 'Unknown')
                result = game.headers.get('Result', '*')
                print(f"{i+1}. {white} vs {black} [{result}]")
        print("\nCommands: <number> (select game), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == 'b':
            return None
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(games):
                broadcast_manager.selected_game = games[idx]
                return broadcast_manager.selected_game
        else:
            print("Invalid option.")

def stream_game_pgn(broadcast_id, round_id, game_id, update_queue, stop_event):
    url = f"https://lichess.org/api/broadcast/{broadcast_id}/round/{round_id}/game/{game_id}.pgn/stream"
    try:
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()
            pgn = ""
            for line in response.iter_lines(decode_unicode=True):
                if stop_event.is_set():
                    break
                if line:
                    pgn += line + "\n"
                elif pgn:  # Blank line might indicate end of a PGN update
                    update_queue.put(pgn)
                    pgn = ""
            if pgn:  # Ensure any remaining PGN is sent
                update_queue.put(pgn)
    except Exception as e:
        print(f"Error streaming PGN: {e}")

def play_game(game_manager, engine, navigator_or_index, current_settings_manager, is_broadcast=False, broadcast_id=None, round_id=None, game_id=None, game_identifier=None):
    if is_broadcast:
        navigator = navigator_or_index
        game_index = None
        update_queue = queue.Queue()
        stop_event = threading.Event()
        streaming_thread = threading.Thread(target=stream_game_pgn, args=(broadcast_id, round_id, game_id, update_queue, stop_event))
        streaming_thread.start()
    else:
        game_index = navigator_or_index
        if not game_manager.games or not (0 <= game_index < len(game_manager.games)):
            print("Invalid game selection or no games available.")
            time.sleep(1)
            return
        original_pgn_game = game_manager.games[game_index]
        navigator = GameNavigator(original_pgn_game)
    clear_screen_and_prepare_for_new_content(is_first_draw=True)
    GAME_VIEW_BLOCK_HEIGHT = 28
    try:
        while True:
            sys.stdout.write(f"\033[{GAME_VIEW_BLOCK_HEIGHT}A")
            for _ in range(GAME_VIEW_BLOCK_HEIGHT):
                sys.stdout.write("\033[2K\n")
            sys.stdout.write(f"\033[{GAME_VIEW_BLOCK_HEIGHT}A")
            sys.stdout.flush()
            lines_printed_this_iteration = 0
            board = navigator.get_current_board()
            title = f"{'Broadcast Game' if is_broadcast else f'Game {game_index + 1}'}: {navigator.working_game.headers.get('White','N/A')} vs {navigator.working_game.headers.get('Black','N/A')}"
            print("\033[2K" + title)
            lines_printed_this_iteration += 1
            if current_settings_manager.get("show_chessboard"):
                move_info = f"Move {board.fullmove_number}. {'White to move' if board.turn == chess.WHITE else 'Black to move'}"
                print("\033[2K" + move_info)
                lines_printed_this_iteration += 1
                board_str = str(board)
                for line in board_str.splitlines():
                    print("\033[2K" + line)
                    lines_printed_this_iteration += 1
            else:
                print(f"\033[2KMove {board.fullmove_number}. {'W' if board.turn == chess.WHITE else 'B'}. (Board printing disabled)")
                lines_printed_this_iteration += 1
            if is_broadcast:
                white_time, black_time = navigator.get_clocks()
                print(f"\033[2KWhite clock: {white_time}, Black clock: {black_time}")
                lines_printed_this_iteration += 1
            current_comment = navigator.current_node.comment
            if current_comment:
                comment_display = current_comment[:70] + '...' if len(current_comment) > 70 else current_comment
                print(f"\033[2KComment: {comment_display}")
                lines_printed_this_iteration += 1
            if board.is_game_over():
                print(f"\033[2KGame over: {board.result()}")
                lines_printed_this_iteration += 1
            variations = navigator.show_variations()
            if variations:
                print("\033[2K\n\033[2KAvailable moves/variations:")
                lines_printed_this_iteration += 2
                for i, var_line in enumerate(variations):
                    if i >= 4:
                        print("\033[2K  ... (more variations exist)")
                        lines_printed_this_iteration += 1
                        break
                    print(f"\033[2K  {var_line}")
                    lines_printed_this_iteration += 1
            if not board.is_game_over() and current_settings_manager.get("lichess_moves_count") > 0:
                get_lichess_data(board, current_settings_manager)
            if is_broadcast:
                while not update_queue.empty():
                    latest_pgn = update_queue.get()
                    navigator.update_from_broadcast_pgn(latest_pgn, game_identifier)
            for _ in range(lines_printed_this_iteration, GAME_VIEW_BLOCK_HEIGHT - 1):
                sys.stdout.write("\033[2K\n")
            sys.stdout.flush()
            print("\033[2KCmds: <mv>|# (e4,Nf3,1), [Ent](main), b(back), a(nalyze), r(ead), p(gn), d # (del var #), m(enu,save), q(menu,no save)")
            command = input("\033[2KCommand: ").strip()
            if command.lower() == 'm':
                if not is_broadcast and navigator.has_changes:
                    game_manager.games[game_index] = navigator.working_game
                    if game_manager.save_games(): print("Changes saved to PGN file.")
                    else: print("Error saving PGN file.")
                    navigator.has_changes = False
                else:
                    print("No changes to save." if not is_broadcast else "Broadcast game, no save needed.")
                time.sleep(0.7)
                break
            elif command.lower() == 'q':
                if not is_broadcast and navigator.has_changes:
                    confirm_quit = input("Unsaved changes. Quit anyway? (y/N): ").strip().lower()
                    if confirm_quit != 'y':
                        continue
                break
            elif command.lower() == 'b':
                if not navigator.go_back(): print("Already at starting position.")
            elif command.lower() == 'r':
                read_board_aloud(board)
            elif command.lower() == 'a':
                if not board.is_game_over():
                    analysis_block_h = get_analysis_block_height(current_settings_manager)
                    print("\n" * (analysis_block_h + 1))
                    sys.stdout.write(f"\033[{analysis_block_h + 1}A")
                    print("\033[2KStarting engine analysis...")
                    stop_event_analyze = threading.Event()
                    analysis_thread_instance = threading.Thread(target=analysis_thread_refined, args=(engine, board.copy(), stop_event_analyze, current_settings_manager))
                    analysis_thread_instance.start()
                    input("\033[2KAnalysis running. Press Enter to stop...")
                    stop_event_analyze.set()
                    analysis_thread_instance.join(timeout=3)
                    clear_analysis_block_dynamic(current_settings_manager)
                    sys.stdout.write("\033[2KAnalysis stopped.\n")
                    for _ in range(analysis_block_h - 1): sys.stdout.write("\033[2K\n")
                    sys.stdout.flush()
                else:
                    print("Cannot analyze finished game position.")
                    time.sleep(1)
            elif command.lower() == 'p':
                clear_screen_and_prepare_for_new_content()
                print(f"--- PGN for {'Broadcast Game' if is_broadcast else f'Game {game_index+1}'} ---")
                print(navigator.get_pgn_string())
                print("-" * 20)
                input("Press Enter to return to game...")
            elif command.lower().startswith('d') and ' ' in command:
                parts = command.split(' ', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    var_num = int(parts[1])
                    success, message = navigator.delete_variation(var_num)
                    print(message)
                    if not success: time.sleep(1)
                    else: time.sleep(0.5); navigator.has_changes = True
                else:
                    print("Invalid delete variation command. Use 'd <number>'.")
                    time.sleep(1)
            else:
                success, move_obj = navigator.make_move(command)
                if success and move_obj:
                    parent_board = navigator.working_game.board()
                    path_to_parent = []
                    temp_n = navigator.current_node.parent
                    while temp_n.parent is not None:
                        path_to_parent.append(temp_n.move)
                        temp_n = temp_n.parent
                    path_to_parent.reverse()
                    for m in path_to_parent: parent_board.push(m)
                    try:
                        display_move = parent_board.san(move_obj)
                    except Exception:
                        display_move = move_obj.uci()
                    print(f"Move made: {display_move}")
                elif command == "" and not success:
                    print("No main line move available or already at end.")
                    time.sleep(1)
                elif not success and command != "":
                    print("Invalid move or command.")
                    time.sleep(1)
    finally:
        if is_broadcast:
            stop_event.set()
            streaming_thread.join()

def main():
    global settings_manager
    print("Enhanced Chess Analyzer - Initializing...")
    pgn_file_cli_arg = sys.argv[1] if len(sys.argv) > 1 else None
    stockfish_cli_override = sys.argv[2] if len(sys.argv) >= 3 else None
    settings_manager = SettingsManager()
    stockfish_path = stockfish_cli_override if stockfish_cli_override else settings_manager.get('engine_path')
    pgn_dir = settings_manager.get('pgn_file_directory')
    if not os.path.isabs(pgn_dir) and pgn_dir != ".":
        pgn_dir = os.path.join(os.getcwd(), pgn_dir)
    os.makedirs(pgn_dir, exist_ok=True)
    pgn_file_to_load = pgn_file_cli_arg if pgn_file_cli_arg else settings_manager.get('default_pgn_filename')
    if os.path.isabs(pgn_file_to_load):
        actual_pgn_path = pgn_file_to_load
    else:
        actual_pgn_path = os.path.join(pgn_dir, pgn_file_to_load)
    print(f"Using PGN: {actual_pgn_path}")
    print(f"Using Engine: {stockfish_path}")
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
    except FileNotFoundError:
        print(f"Error: Stockfish engine not found at '{stockfish_path}'.")
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing Stockfish engine: {e}")
        sys.exit(1)
    game_manager = GameManager(actual_pgn_path)
    clear_screen_and_prepare_for_new_content(is_first_draw=True)
    print("Welcome to Enhanced Chess Analyzer!")
    time.sleep(0.5)
    try:
        while True:
            selected_game_idx = show_game_selection_menu(game_manager, settings_manager)
            if selected_game_idx is None:
                break
            play_game(game_manager, engine, selected_game_idx, settings_manager)
    finally:
        clear_screen_and_prepare_for_new_content()
        print("Quitting engine...")
        engine.quit()
        print("Program exited.")

if __name__ == "__main__":
    main()
