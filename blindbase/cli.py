"""Console entry point for BlindBase.

This module gathers the interactive text-based UI that used to live in the
monolithic *blindbase.py*.  It stitches together the refactored components
(settings, storage, broadcast, analysis, navigator, etc.) so behaviour remains
unchanged.  Eventually we will migrate to Typer/Rich, but for now we keep the
same imperative flow.
"""
from __future__ import annotations

import queue
import threading
import time
import sys
import os
from datetime import datetime
from urllib.parse import quote
import re
import shutil
import io
import json

import chess
import chess.engine
import chess.pgn
import requests

from blindbase.settings import SettingsManager
from blindbase.storage import GameManager
from blindbase.broadcast import BroadcastManager, stream_game_pgn
from blindbase.navigator import GameNavigator
from blindbase.analysis import (
    get_analysis_block_height,
    clear_analysis_block_dynamic,
    print_analysis_refined,
    analysis_thread_refined,
)
from blindbase.ui.utils import clear_screen_and_prepare_for_new_content, UI_SCREEN_BUFFER_HEIGHT

# ---------------------------------------------------------------------------
# Utility helpers that were previously top-level in the monolith
# ---------------------------------------------------------------------------

def read_board_aloud(board: chess.Board):
    clear_screen_and_prepare_for_new_content()
    print("--- BOARD READING ---")
    piece_order_map = {
        chess.KING: 0,
        chess.QUEEN: 1,
        chess.ROOK: 2,
        chess.BISHOP: 3,
        chess.KNIGHT: 4,
        chess.PAWN: 5,
    }
    piece_chars = {
        chess.PAWN: "",
        chess.ROOK: "R",
        chess.KNIGHT: "N",
        chess.BISHOP: "B",
        chess.QUEEN: "Q",
        chess.KING: "K",
    }
    pieces_data = []
    for sq_idx in chess.SQUARES:
        pc = board.piece_at(sq_idx)
        if pc:
            sq_name = chess.square_name(sq_idx)
            disp_str = (
                piece_chars[pc.piece_type] + sq_name
                if pc.piece_type != chess.PAWN
                else sq_name
            )
            pieces_data.append(
                {
                    "display": disp_str,
                    "color": pc.color,
                    "type": pc.piece_type,
                    "file": chess.square_file(sq_idx),
                    "rank": chess.square_rank(sq_idx),
                }
            )
    sort_key = lambda p: (piece_order_map[p["type"]], p["file"], p["rank"])  # type: ignore[index]
    wp = [p["display"] for p in sorted([pd for pd in pieces_data if pd["color"] == chess.WHITE], key=sort_key)]
    bp = [p["display"] for p in sorted([pd for pd in pieces_data if pd["color"] == chess.BLACK], key=sort_key)]
    print("White Pieces:")
    if wp:
        for p_str in wp:
            print(f"  {p_str}")
    else:
        print("  None")
    print("\nBlack Pieces:")
    if bp:
        for p_str in bp:
            print(f"  {p_str}")
    else:
        print("  None")
    print("-" * 20)
    input("Press Enter to continue...")


def get_lichess_data(board: chess.Board, settings_manager: SettingsManager):
    fen = board.fen()
    fen_enc = quote(fen)
    url = f"https://explorer.lichess.ovh/masters?fen={fen_enc}"
    num_moves = settings_manager.get("lichess_moves_count")
    if num_moves == 0:
        return
    print("\n--- Lichess Masters Database ---")
    try:
        resp = requests.get(url, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        op_name = "N/A"
        op_info = data.get("opening")
        if op_info:
            op_name = op_info.get("name", "N/A")
        if op_name != "N/A":
            print(f"Opening: {op_name}")
        moves = data.get("moves", [])
        if moves:
            print(f"Top {min(num_moves, len(moves))} moves:")
            for m_data in moves[:num_moves]:
                tot = m_data["white"] + m_data["draws"] + m_data["black"]
                if tot > 0:
                    wp, dp, bp = (
                        m_data["white"] / tot * 100,
                        m_data["draws"] / tot * 100,
                        m_data["black"] / tot * 100,
                    )
                    print(
                        f"  {m_data['san']}: {tot} games (W:{wp:.0f}%, D:{dp:.0f}%, B:{bp:.0f}%)"
                    )
        else:
            print("No Lichess Masters data for this position.")
    except requests.exceptions.Timeout:
        print("Lichess Masters: Request timed out.")
    except requests.exceptions.RequestException as e:
        print(f"Lichess Masters: Error - {e}")
    except Exception as e:
        print(f"Lichess Masters: Processing error - {e}")


# ---------------------------------------------------------------------------
# Settings menu and game selection (copied verbatim, minor imports adjusted)
# ---------------------------------------------------------------------------

def show_settings_menu(settings_manager: SettingsManager):
    while True:
        clear_screen_and_prepare_for_new_content()
        print("--- SETTINGS MENU ---")
        print(f"1. Lichess Moves Count (current: {settings_manager.get('lichess_moves_count')})")
        print(f"2. Engine Analysis Lines (current: {settings_manager.get('engine_lines_count')})")
        print(f"3. Show Chessboard (current: {'Yes' if settings_manager.get('show_chessboard') else 'No'})")
        print(f"4. Analysis Block Padding (current: {settings_manager.get('analysis_block_padding')})")
        print(f"5. Engine Path (current: {settings_manager.get('engine_path')})")
        print(f"6. PGN File Directory (current: {settings_manager.get('pgn_file_directory')})")
        print(f"7. Default PGN Filename (current: {settings_manager.get('default_pgn_filename')})")
        print(f"8. Games Per Page in Menu (current: {settings_manager.get('games_per_page')})")
        print("9. Back to Game Selection")
        choice = input("\nSelect option: ").strip()
        if choice == "1":
            try:
                val = int(
                    input(
                        f"New Lichess moves count (0-10, current {settings_manager.get('lichess_moves_count')}): "
                    )
                )
                settings_manager.set("lichess_moves_count", max(0, min(10, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == "2":
            try:
                val = int(
                    input(
                        f"New engine lines count (1-10, current {settings_manager.get('engine_lines_count')}): "
                    )
                )
                settings_manager.set("engine_lines_count", max(1, min(10, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == "3":
            settings_manager.set("show_chessboard", not settings_manager.get("show_chessboard"))
        elif choice == "4":
            try:
                val = int(
                    input(
                        f"New analysis padding lines (0-5, current {settings_manager.get('analysis_block_padding')}): "
                    )
                )
                settings_manager.set("analysis_block_padding", max(0, min(5, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == "5":
            val = input(
                f"New engine path (current {settings_manager.get('engine_path')}): "
            ).strip()
            if val:
                settings_manager.set("engine_path", val)
        elif choice == "6":
            val = input(
                f"New PGN file directory (current {settings_manager.get('pgn_file_directory')}): "
            ).strip()
            if val:
                settings_manager.set("pgn_file_directory", val)
        elif choice == "7":
            val = input(
                f"New default PGN filename (current {settings_manager.get('default_pgn_filename')}): "
            ).strip()
            if val:
                settings_manager.set("default_pgn_filename", val)
        elif choice == "8":
            try:
                val = int(
                    input(
                        f"New games per page (5-50, current {settings_manager.get('games_per_page')}): "
                    )
                )
                settings_manager.set("games_per_page", max(5, min(50, val)))
            except ValueError:
                print("Invalid number.")
        elif choice == "9":
            break
        else:
            print("Invalid option.")
        if choice in [str(i) for i in range(1, 9)]:
            print("Setting updated.")
            time.sleep(0.7)


# ---------------------------------------------------------------------------
# Game selection & broadcast menus (copied from legacy script)
# ---------------------------------------------------------------------------

current_games_page = 0

def show_games_menu(broadcast_manager):
    games = broadcast_manager.fetch_games(broadcast_manager.selected_round["id"])
    while True:
        clear_screen_and_prepare_for_new_content()
        print(f"--- GAMES for {broadcast_manager.selected_round['name']} ---")
        if not games:
            print("No games available.")
        else:
            for i, game in enumerate(games):
                white = game.headers.get("White", "Unknown")
                black = game.headers.get("Black", "Unknown")
                result = game.headers.get("Result", "*")
                print(f"{i+1}. {white} vs {black} [{result}]")
        print("\nCommands: <number> (select game), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == "b":
            return None
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(games):
                broadcast_manager.selected_game = games[idx]
                return broadcast_manager.selected_game
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
                name = round.get("name", "Unknown")
                start_date = round.get("startDate", "Unknown")
                print(f"{i+1}. {name} (Start: {start_date})")
        print("\nCommands: <number> (select round), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == "b":
            return None
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(rounds):
                broadcast_manager.selected_round = rounds[idx]
                return show_games_menu(broadcast_manager)
        else:
            print("Invalid option.")

def show_broadcasts_menu(broadcast_manager):
    while True:
        clear_screen_and_prepare_for_new_content()
        print("--- BROADCASTS MENU ---")
        if not broadcast_manager.broadcasts:
            print("No broadcasts available.")
        else:
            for i, broadcast in enumerate(broadcast_manager.broadcasts):
                name = broadcast.get("name", "Unknown")
                start_date = broadcast.get("startDate", "Unknown")
                print(f"{i+1}. {name} (Start: {start_date})")
        print("\nCommands: <number> (select broadcast), 'r' (refresh), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == "b":
            return None
        elif choice.lower() == "r":
            broadcast_manager.fetch_broadcasts()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(broadcast_manager.broadcasts):
                broadcast_manager.selected_broadcast = broadcast_manager.broadcasts[idx]
                return show_rounds_menu(broadcast_manager)
        else:
            print("Invalid option.")

def show_game_selection_menu(game_manager, settings_manager, engine):
    global current_games_page
    is_first_call_of_session = True
    games_per_page = settings_manager.get("games_per_page")
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
            print(
                f"\033[2KTotal games: {total_games}. Displaying {start_index+1}-{end_index} (Page {current_games_page+1} of {total_pages})"
            )
            print(
                f"\033[2KCurrent selection: {game_manager.current_game_index + 1 if game_manager.games else 'N/A'}"
            )
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
                    print(
                        f"\033[2K{marker}{i+1:3d}. {white} vs {black} [{result}] {date}{event_str}"
                    )
                else:
                    print("\033[2K")
            cmd_list = [
                "<num> (view)",
                "'n'(new)",
                "'s'(set)",
                "'r'(reload)",
                "'b'(broadcasts)",
            ]
            if total_pages > 1:
                if current_games_page > 0:
                    cmd_list.append("'p'(prev page)")
                if current_games_page < total_pages - 1:
                    cmd_list.append("'f'(next page)")
            cmd_list.extend(["'d <num>'(del)", "'q'(quit)"])
            print(f"\033[2KCmds: {', '.join(cmd_list)}")
        print("\033[2KCommand: ", end="", flush=True)
        choice = input().strip().lower()
        cmd_parts = choice.split()
        action = cmd_parts[0] if cmd_parts else ""
        if action == "q":
            return None
        elif action == "n":
            if game_manager.add_new_game():
                if game_manager.save_games():
                    print("\033[2KNew game added and PGN saved.")
                else:
                    print("\033[2KNew game added, but error saving PGN.")
                return game_manager.current_game_index
        elif action == "s":
            show_settings_menu(settings_manager)
            is_first_call_of_session = True
        elif action == "r":
            game_manager.load_games()
            print("\033[2KPGN file reloaded.")
            time.sleep(1)
        elif action == "b":
            broadcast_manager = BroadcastManager()
            if broadcast_manager.fetch_broadcasts():
                selected_game = show_broadcasts_menu(broadcast_manager)
                if selected_game:
                    navigator = GameNavigator(selected_game)
                    play_game(
                        None,
                        engine,
                        navigator,
                        settings_manager,
                        is_broadcast=True,
                        broadcast_id=broadcast_manager.selected_broadcast["id"],
                        round_id=broadcast_manager.selected_round["id"],
                        game_id=selected_game.game_id,
                        game_identifier=(selected_game.headers["White"], selected_game.headers["Black"]),
                    )
            is_first_call_of_session = True
        elif action in ("f", "next"):
            total_games = len(game_manager.games)
            total_pages = (total_games + games_per_page - 1) // games_per_page
            if total_pages > 1 and current_games_page < total_pages - 1:
                current_games_page += 1
            else:
                print("\033[2KAlready on the last page or no multiple pages.")
                time.sleep(0.5)
        elif action in ("p", "prev"):
            if total_pages > 1 and current_games_page > 0:
                current_games_page -= 1
            else:
                print("\033[2KAlready on the first page or no multiple pages.")
                time.sleep(0.5)
        elif action == "d" and len(cmd_parts) > 1 and cmd_parts[1].isdigit():
            if not game_manager.games:
                print("\033[2KNo games to delete.")
                time.sleep(1)
                continue
            game_num_to_delete_1_indexed = int(cmd_parts[1])
            game_num_to_delete_0_indexed = game_num_to_delete_1_indexed - 1
            if 0 <= game_num_to_delete_0_indexed < len(game_manager.games):
                game_desc = (
                    f"{game_manager.games[game_num_to_delete_0_indexed].headers.get('White','?')} vs {game_manager.games[game_num_to_delete_0_indexed].headers.get('Black','?')}"
                )
                confirm = input(
                    f"\033[2KDelete game {game_num_to_delete_1_indexed} ({game_desc})? (y/N): "
                ).lower()
                if confirm == "y":
                    del game_manager.games[game_num_to_delete_0_indexed]
                    print("\033[2KGame deleted.")
                    if game_manager.current_game_index > game_num_to_delete_0_indexed:
                        game_manager.current_game_index -= 1
                    elif (
                        game_manager.current_game_index == game_num_to_delete_0_indexed
                        and game_manager.current_game_index >= len(game_manager.games)
                    ):
                        game_manager.current_game_index = (
                            max(0, len(game_manager.games) - 1 if game_manager.games else 0)
                        )
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


# ---------------------------------------------------------------------------
# play_game function (unchanged except engine arg passed in)
# ---------------------------------------------------------------------------

def play_game(
    game_manager,
    engine,
    navigator_or_index,
    settings_manager,
    *,
    is_broadcast=False,
    broadcast_id=None,
    round_id=None,
    game_id=None,
    game_identifier=None,
):
    # Copied verbatim from legacy script with minimal tweaks.
    if is_broadcast:
        navigator = navigator_or_index
        game_index = None
        update_queue = queue.Queue()
        stop_event = threading.Event()
        streaming_thread = threading.Thread(
            target=stream_game_pgn,
            args=(round_id, game_id, update_queue, stop_event),
        )
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
            title = (
                "Broadcast Game"
                if is_broadcast
                else f"Game {game_index + 1}: {navigator.working_game.headers.get('White','N/A')} vs {navigator.working_game.headers.get('Black','N/A')}"
            )
            print("\033[2K" + title)
            lines_printed_this_iteration += 1
            if settings_manager.get("show_chessboard"):
                move_info = f"Move {board.fullmove_number}. {'White to move' if board.turn == chess.WHITE else 'Black to move'}"
                print("\033[2K" + move_info)
                lines_printed_this_iteration += 1
                board_str = str(board)
                for line in board_str.splitlines():
                    print("\033[2K" + line)
                    lines_printed_this_iteration += 1
            else:
                print(
                    f"\033[2KMove {board.fullmove_number}. {'W' if board.turn == chess.WHITE else 'B'}. (Board printing disabled)"
                )
                lines_printed_this_iteration += 1
            if is_broadcast:
                white_time, black_time = navigator.get_clocks()
                print(f"\033[2KWhite clock: {white_time}, Black clock: {black_time}")
                lines_printed_this_iteration += 1
            current_comment = navigator.current_node.comment
            if current_comment:
                comment_display = (
                    current_comment[:70] + "..." if len(current_comment) > 70 else current_comment
                )
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
            if not board.is_game_over() and settings_manager.get("lichess_moves_count") > 0:
                get_lichess_data(board, settings_manager)
            if is_broadcast:
                while not update_queue.empty():
                    latest_pgn = update_queue.get()
                    navigator.update_from_broadcast_pgn(latest_pgn, game_identifier)
            for _ in range(lines_printed_this_iteration, GAME_VIEW_BLOCK_HEIGHT - 1):
                sys.stdout.write("\033[2K\n")
            sys.stdout.flush()
            print(
                "\033[2KCmds: <mv>|# (e4,Nf3,1), [Ent](main), b(back), a(nalyze), r(ead), p(gn), d # (del var #), m(enu,save), q(menu,no save)"
            )
            command = input("\033[2KCommand: ").strip()
            if command.lower() == "m":
                if not is_broadcast and navigator.has_changes:
                    game_manager.games[game_index] = navigator.working_game
                    if game_manager.save_games():
                        print("Changes saved to PGN file.")
                    else:
                        print("Error saving PGN file.")
                    navigator.has_changes = False
                else:
                    print("No changes to save." if not is_broadcast else "Broadcast game, no save needed.")
                time.sleep(0.7)
                break
            elif command.lower() == "q":
                if not is_broadcast and navigator.has_changes:
                    confirm_quit = input("Unsaved changes. Quit anyway? (y/N): ").strip().lower()
                    if confirm_quit != "y":
                        continue
                break
            elif command.lower() == "b":
                if not navigator.go_back():
                    print("Already at starting position.")
            elif command.lower() == "r":
                read_board_aloud(board)
            elif command.lower() == "a":
                if not board.is_game_over():
                    analysis_block_h = get_analysis_block_height(settings_manager)
                    print("\n" * (analysis_block_h + 1))
                    sys.stdout.write(f"\033[{analysis_block_h + 1}A")
                    print("\033[2KStarting engine analysis...")
                    stop_event_analyze = threading.Event()
                    analysis_thread_instance = threading.Thread(
                        target=analysis_thread_refined,
                        args=(engine, board.copy(), stop_event_analyze, settings_manager),
                    )
                    analysis_thread_instance.start()
                    input("\033[2KAnalysis running. Press Enter to stop...")
                    stop_event_analyze.set()
                    analysis_thread_instance.join(timeout=3)
                    clear_analysis_block_dynamic(settings_manager)
                    sys.stdout.write("\033[2KAnalysis stopped.\n")
                    for _ in range(analysis_block_h - 1):
                        sys.stdout.write("\033[2K\n")
                    sys.stdout.flush()
                else:
                    print("Cannot analyze finished game position.")
                    time.sleep(1)
            elif command.lower() == "p":
                clear_screen_and_prepare_for_new_content()
                print(
                    f"--- PGN for {'Broadcast Game' if is_broadcast else f'Game {game_index+1}'} ---"
                )
                print(navigator.get_pgn_string())
                print("-" * 20)
                input("Press Enter to return to game...")
            elif command.lower().startswith("d") and " " in command:
                parts = command.split(" ", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    var_num = int(parts[1])
                    success, message = navigator.delete_variation(var_num)
                    print(message)
                    if not success:
                        time.sleep(1)
                    else:
                        time.sleep(0.5)
                        navigator.has_changes = True
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
                    for m in path_to_parent:
                        parent_board.push(m)
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


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    """Launch the classic text CLI."""

    print("Enhanced Chess Analyzer – Initializing...")
    pgn_file_cli_arg = sys.argv[1] if len(sys.argv) > 1 else None
    stockfish_cli_override = sys.argv[2] if len(sys.argv) >= 3 else None

    settings_manager = SettingsManager()

    stockfish_path = (
        stockfish_cli_override if stockfish_cli_override else settings_manager.get("engine_path")
    )

    pgn_dir = settings_manager.get("pgn_file_directory")
    if not os.path.isabs(pgn_dir) and pgn_dir != ".":
        pgn_dir = os.path.join(os.getcwd(), pgn_dir)
    os.makedirs(pgn_dir, exist_ok=True)

    pgn_file_to_load = (
        pgn_file_cli_arg if pgn_file_cli_arg else settings_manager.get("default_pgn_filename")
    )
    actual_pgn_path = (
        pgn_file_to_load if os.path.isabs(pgn_file_to_load) else os.path.join(pgn_dir, pgn_file_to_load)
    )

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
            selected_game_idx = show_game_selection_menu(game_manager, settings_manager, engine)
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