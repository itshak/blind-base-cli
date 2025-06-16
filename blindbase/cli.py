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
from pathlib import Path
import platform
import re
import shutil
import io
import json

import chess
import chess.engine
import chess.pgn
import requests

# ------------------------------------------------------------------
# Fallback: ensure move_to_str is always defined early (some frozen
# builds seem to lose late definitions causing NameError at runtime).
# The full featured definition remains later in the file; this minimal
# version will be overwritten, but guarantees the symbol exists when
# functions defined earlier reference it.
# ------------------------------------------------------------------

def _basic_move_to_str(board: 'chess.Board', move: 'chess.Move', style: str) -> str:  # noqa: F821
    """Simple SAN/ UCI fallback in case the full version is not loaded yet."""
    style = (style or "san").lower()
    if style == "uci":
        return move.uci()
    try:
        return board.san(move)
    except Exception:
        return move.uci()

# Expose name for early references; later full definition will overwrite.
move_to_str = _basic_move_to_str

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
from blindbase.ui.utils import clear_screen_and_prepare_for_new_content

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
    piece_words = {
        chess.PAWN: "Pawn",
        chess.ROOK: "Rook",
        chess.KNIGHT: "Knight",
        chess.BISHOP: "Bishop",
        chess.QUEEN: "Queen",
        chess.KING: "King",
    }
    pieces_data = []
    for sq_idx in chess.SQUARES:
        pc = board.piece_at(sq_idx)
        if pc:
            sq_name = chess.square_name(sq_idx)
            style_pref = SettingsManager().get('move_notation')
            square_disp = format_square(sq_name, style_pref)
            notation_style = style_pref.lower()
            if notation_style in {"literate", "nato", "anna"}:
                if pc.piece_type == chess.PAWN:
                    disp_str = square_disp
                else:
                    disp_str = f"{piece_words[pc.piece_type]} {square_disp}"
            else:
                if pc.piece_type == chess.PAWN:
                    disp_str = square_disp
                else:
                    disp_str = piece_chars[pc.piece_type] + square_disp
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


def fetch_masters_moves(board: chess.Board, settings_manager: SettingsManager):
    """Return list of (san, stats str) for top moves from Lichess Masters."""
    num_moves = settings_manager.get("lichess_moves_count")
    if num_moves == 0:
        return []
    fen_enc = quote(board.fen())
    url = f"https://explorer.lichess.ovh/masters?fen={fen_enc}"
    try:
        resp = requests.get(url, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        moves_out = []
        for m_data in data.get("moves", [])[:num_moves]:
            tot = m_data["white"] + m_data["draws"] + m_data["black"]
            if tot == 0:
                continue
            wp, dp, bp = (
                m_data["white"] / tot * 100,
                m_data["draws"] / tot * 100,
                m_data["black"] / tot * 100,
            )
            stats = f"{tot} games (W:{wp:.0f}%, D:{dp:.0f}%, B:{bp:.0f}%)"
            moves_out.append((m_data["san"], stats))
        return moves_out
    except Exception:
        return []


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
        print(f"9. Move notation style (current: {settings_manager.get('move_notation')})")
        print("10. Go Back")
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
                input("Press Enter to continue...")
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
                input("Press Enter to continue...")
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
                input("Press Enter to continue...")
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
                input("Press Enter to continue...")
        elif choice == "9":
            print("Select notation style:")
            print("1. uci   (e2e4)")
            print("2. san   (Nxf3)")
            print("3. literate  (Knight takes f 3)")
            print("4. nato  (Knight takes foxtrot 3)")
            print("5. anna  (Knight takes felix 3)")
            sel = input("Choose 1-5: ").strip()
            mapping = {"1":"uci","2":"san","3":"literate","4":"nato","5":"anna"}
            if sel in mapping:
                settings_manager.set('move_notation', mapping[sel])
                print("Notation updated.")
                time.sleep(0.7)
        elif choice == "10":
            break
        else:
            print("Invalid option.")
            input("Press Enter to continue...")
        if choice in [str(i) for i in range(1, 10)]:
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
            return "BACK"
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(games):
                broadcast_manager.selected_game = games[idx]
                return broadcast_manager.selected_game
        elif choice.lower() == 'm':
            show_main_menu(None, SettingsManager(), None)
            continue
        elif choice.lower() == 'h':
            show_help('broadcast_menus')
            continue
        else:
            print("Invalid option.")
            input("Press Enter to continue...")

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
                # 'startsAt' is epoch millis; convert if present
                ts = round.get('startsAt') or round.get('startsAfterPrevious') or round.get('createdAt')
                if ts:
                    try:
                        import datetime as _dt
                        start_date = _dt.datetime.utcfromtimestamp(ts/1000).strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        start_date = str(ts)
                else:
                    start_date = 'Unknown'
                print(f"{i+1}. {name} (Start: {start_date})")
        print("\nCommands: <number> (select round), 'b' (back)")
        choice = input("Select option: ").strip()
        if choice.lower() == "b":
            return "BACK"
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(rounds):
                broadcast_manager.selected_round = rounds[idx]
                res = show_games_menu(broadcast_manager)
                if res == "BACK":
                    continue
                else:
                    return res
        elif choice.lower() == 'm':
            show_main_menu(None, SettingsManager(), None)
            continue
        elif choice.lower() == 'h':
            show_help('broadcast_menus')
            continue
        else:
            print("Invalid option.")
            input("Press Enter to continue...")

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
                res = show_rounds_menu(broadcast_manager)
                if res == "BACK":
                    continue
                else:
                    return res
        elif choice.lower() == 'm':
            show_main_menu(None, SettingsManager(), None)
            continue
        elif choice.lower() == 'h':
            show_help('broadcast_menus')
            continue
        else:
            print("Invalid option.")
            input("Press Enter to continue...")

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
            sys.stdout.write("\033[H\033[J")
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
        if choice == 'm':
            show_main_menu(game_manager, settings_manager, engine)
            is_first_call_of_session = True
            continue
        if choice == 'h':
            show_help('game_selection')
            is_first_call_of_session = True
            continue
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
            return "BROADCAST"
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
            # Note: in-game commands like 't' (Masters tree) and 'a' (analysis) are handled inside play_game(), not here.
            pass
    # end while loop


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
    # Track how many lines were printed in previous iteration so we can clear them
    display_height = 0  # dynamic, ensures compact output
    if is_broadcast:
        navigator = GameNavigator(navigator_or_index)
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
            sys.stdout.write("\033[H\033[J")
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
                last_move_san = "-"
                if navigator.current_node.parent is not None:
                    temp_board = navigator.current_node.parent.board()
                    try:
                        last_move_san = move_to_str(temp_board, navigator.current_node.move, settings_manager.get('move_notation'))
                    except Exception:
                        last_move_san = navigator.current_node.move.uci()
                from blindbase.ui.accessibility import screen_reader_mode
                if not screen_reader_mode():
                    from blindbase.ui.board import render_board, get_console
                    console = get_console()
                    for text_row in render_board(board):
                        console.print(text_row)
                        lines_printed_this_iteration += 1
                else:
                    board_str = str(board)
                    for line in board_str.splitlines():
                        print("\033[2K" + line)
                        lines_printed_this_iteration += 1
                # After board rows, show turn & last move info
                turn_str = "white" if board.turn == chess.WHITE else "black"
                print(f"\033[2KTurn: {turn_str}")
                lines_printed_this_iteration += 1
                if last_move_san != "-":
                    move_num_disp = (board.fullmove_number - 1) if board.turn == chess.WHITE else board.fullmove_number
                    print(f"\033[2KLast move: {move_num_disp}.{last_move_san}")
                else:
                    print("\033[2KLast move: Initial position")
                lines_printed_this_iteration += 1
            else:
                turn_str = "white" if board.turn == chess.WHITE else "black"
                print(f"\033[2KTurn: {turn_str} (board hidden)")
                lines_printed_this_iteration += 1
            if is_broadcast:
                white_time, black_time = navigator.get_clocks()
                print(f"\033[2KWhite clock: {white_time}, Black clock: {black_time}")
                lines_printed_this_iteration += 1
            current_comment = navigator.current_node.comment or ""
            if current_comment:
                # Remove clock tags from comment
                import re
                cleaned = re.sub(r"\[%clk\s+\d+:\d{2}:\d{2}\]", "", current_comment).strip()
                if cleaned:  # Only show if something besides clock remains
                    comment_display = cleaned[:70] + "..." if len(cleaned) > 70 else cleaned
                    print(f"\033[2KComment: {comment_display}")
                    lines_printed_this_iteration += 1
            if board.is_game_over():
                print(f"\033[2KGame over: {board.result()}")
                lines_printed_this_iteration += 1
            # Save core_lines_count before printing variations/footer
            core_lines_count = lines_printed_this_iteration

            variations_nodes = navigator.current_node.variations
            if variations_nodes:
                print("\033[2K\n\033[2KNext moves:")
                lines_printed_this_iteration += 2
                style_pref = settings_manager.get('move_notation')
                for i, var_node in enumerate(variations_nodes):
                    if i >= 4:
                        print("\033[2K  ... (more variations exist)")
                        lines_printed_this_iteration += 1
                        break
                    disp = move_to_str(board.copy(), var_node.move, style_pref)
                    print(f"\033[2K  {i+1}. {disp}")
                    lines_printed_this_iteration += 1
            # Masters data will be shown on demand via 't' command
            if is_broadcast:
                while not update_queue.empty():
                    latest_pgn = update_queue.get()
                    navigator.update_from_broadcast_pgn(latest_pgn, game_identifier)
            # Update the display_height for next refresh so we clear exactly what we printed
            footer_clear_height = (lines_printed_this_iteration + 1) - core_lines_count
            display_height = lines_printed_this_iteration + 1  # command prompt line only
            sys.stdout.flush()
            command = input("\033[2Kcommand (h for help): ").strip()
            # Global commands
            if command.lower() == "m":
                show_main_menu(game_manager, settings_manager, engine)
                continue
            if command.lower() == "h":
                show_help("game_view")
                continue

            if command.lower() == "settings":
                show_settings_menu(settings_manager)
                # After returning from settings, the loop will redraw the board, applying changes.
                continue

            if command.lower() == "q":
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
                if engine is None:
                    print("Engine not available. Configure engine path in settings first.")
                    continue
                if not board.is_game_over():
                    analysis_block_h = get_analysis_block_height(settings_manager)
                    # Clear existing footer (variations/cmds) lines below board
                    sys.stdout.write(f"\033[{footer_clear_height}A")
                    for _ in range(footer_clear_height):
                        sys.stdout.write("\033[2K\n")
                    sys.stdout.write(f"\033[{footer_clear_height}A")

                    # Reserve space for engine output below board
                    print("\n" * analysis_block_h, end="")
                    # Static instruction + prompt line
                    print("Enter the line number to follow or 'b' to go back")
                    stop_event_analyze = threading.Event()
                    shared_pv: dict[int, chess.Move] = {}
                    analysis_thread_instance = threading.Thread(
                        target=analysis_thread_refined,
                        args=(engine, board.copy(), stop_event_analyze, settings_manager, shared_pv)
                    )
                    analysis_thread_instance.start()
                    while True:
                        user_inp = input("\033[2K> ").strip()
                        if user_inp == "" or user_inp.lower() == "b":
                            break
                        if user_inp.isdigit():
                            var_num = int(user_inp)
                            if var_num in shared_pv:
                                move_obj = shared_pv[var_num]
                                navigator.make_move(move_obj.uci())
                                break
                            else:
                                print("Variation not ready yet.")
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
            elif command.lower() == "t":
                # Clear footer (variations/cmds) lines below board before showing Masters tree
                sys.stdout.write(f"\033[{footer_clear_height}A")
                for _ in range(footer_clear_height):
                    sys.stdout.write("\033[2K\n")
                sys.stdout.write(f"\033[{footer_clear_height}A")

                print("--- Opening tree ---")
                masters_moves = fetch_masters_moves(board, settings_manager)
                if not masters_moves:
                    print("No Masters data available.")
                    time.sleep(1)
                else:
                    for idx, (san, stats) in enumerate(masters_moves, 1):
                        try:
                            mv = board.parse_san(san)
                            san_disp = move_to_str(board.copy(), mv, settings_manager.get('move_notation'))
                        except Exception:
                            san_disp = san
                        print(f"  {idx}. {san_disp}  {stats}")
                    choice = input("Select move number or 'b' to cancel: ").strip()
                    if choice.isdigit():
                        num = int(choice)
                        if 1 <= num <= len(masters_moves):
                            sel_san = masters_moves[num-1][0]
                            success, _ = navigator.make_move(sel_san)
                            if not success:
                                print("Invalid move from Masters list.")
                                time.sleep(1)

            # -------------------- NEW COMMANDS --------------------
            elif command.lower().startswith("p") and command.lower() not in ("pg", "pgn"):
                # Piece location announcement: 'p N' etc.
                parts = command.split(maxsplit=1)
                piece_code = parts[1] if len(parts) == 2 else command[1:]
                if not piece_code:
                    piece_code = input("Enter piece code (e.g., N, k, A): ").strip()
                style_pref = settings_manager.get('move_notation')
                msg = describe_piece_locations_formatted(board, piece_code, style_pref)
                print(msg)
                input("Press Enter to continue...")

            elif command.lower().startswith("s"):
                # Rank/File announcement: 's a' or 's 1'
                parts = command.split(maxsplit=1)
                spec = parts[1] if len(parts) == 2 else command[1:]
                if not spec:
                    spec = input("Enter file (a-h) or rank (1-8): ").strip()
                style_pref = settings_manager.get('move_notation')
                msg = describe_file_or_rank_formatted(board, spec, style_pref)
                print(msg)
                input("Press Enter to continue...")

            elif command.lower() in ("eval", "c"):
                try:
                    info = engine.analyse(board.copy(), chess.engine.Limit(depth=18))
                    score = info["score"].white()
                    depth = info.get("depth", 0)
                    if score.is_mate():
                        val_str = f"M{score.mate()}"
                    else:
                        cp = score.score(mate_score=100000)
                        val_str = f"{cp/100:+.2f}"
                    print(f"{val_str} (depth {depth})")
                except Exception as e:
                    print(f"Error getting evaluation: {e}")
                input("Press Enter to continue...")

            elif command.lower() == "prev":
                if not navigator.go_back():
                    print("Already at starting position.")
                time.sleep(0.5)

            elif command.lower() == "next":
                success, _ = navigator.make_move("")
                if not success:
                    print("No main line move available or already at end.")
                    time.sleep(1)

            elif command.lower() in ("pg", "pgn"):
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
            elif command.lower() == "save":
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
                    input("Press Enter to continue...")
    except Exception as e:
        # Log unexpected errors but avoid crashing the whole program
        print(f"Unexpected error: {e}")
        import traceback; traceback.print_exc()
        input("Press Enter to continue...")
    finally:
        if is_broadcast:
            stop_event.set()
            streaming_thread.join()


# ---------------------------------------------------------------------------
# New helpers for granular board announcements (piece/file/rank)
# ---------------------------------------------------------------------------

def get_squares_for_piece(board: chess.Board, piece_code: str) -> list[str]:
    """Return list of square names matching *piece_code*.

    piece_code examples:
        'N' – white knights, 'k' – black king, 'A' – all white pieces, 'a' – all black pieces.
    """
    if not piece_code:
        return []
    code = piece_code[0]
    # Handle special 'A' / 'a' -> all pieces of one colour
    if code in ("A", "a"):
        colour = chess.WHITE if code.isupper() else chess.BLACK
        return [chess.square_name(sq) for sq, pc in board.piece_map().items() if pc.color == colour]
    # Map to piece type
    piece_map = {
        "p": chess.PAWN,
        "n": chess.KNIGHT,
        "b": chess.BISHOP,
        "r": chess.ROOK,
        "q": chess.QUEEN,
        "k": chess.KING,
    }
    piece_type = piece_map.get(code.lower())
    if piece_type is None:
        return []
    colour = chess.WHITE if code.isupper() else chess.BLACK
    squares = [chess.square_name(sq) for sq, pc in board.piece_map().items() if pc.color == colour and pc.piece_type == piece_type]
    return squares


def describe_piece_locations(board: chess.Board, piece_code: str) -> str:
    # Handle 'A' / 'a' (all pieces of one colour)
    if piece_code.lower() == "a":
        # List all pieces of given colour with square names
        colour = chess.WHITE if piece_code.isupper() else chess.BLACK
        piece_chars = {chess.PAWN:"", chess.ROOK:"R", chess.KNIGHT:"N", chess.BISHOP:"B", chess.QUEEN:"Q", chess.KING:"K"}
        pieces = []
        piece_priority = {chess.KING:0, chess.QUEEN:1, chess.ROOK:2, chess.BISHOP:3, chess.KNIGHT:4, chess.PAWN:5}
        for sq, pc in board.piece_map().items():
            if pc.color == colour:
                disp = (piece_chars[pc.piece_type] + chess.square_name(sq)) if pc.piece_type != chess.PAWN else chess.square_name(sq)
                pieces.append((piece_priority[pc.piece_type], disp))
        pieces.sort(key=lambda t: (t[0], t[1]))
        disp_list = [d for _, d in pieces]
        colour_str_local = "White" if colour == chess.WHITE else "Black"
        if disp_list:
            return f"{colour_str_local} pieces: " + ", ".join(disp_list) + "."
        else:
            return f"{colour_str_local} pieces: none."

    # -----------------------------------------
    colour_str = "White" if piece_code.isupper() else "Black"
    squares = get_squares_for_piece(board, piece_code)
    singular = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}
    plural = {k: v + ("s" if not v.endswith("s") else "") for k, v in singular.items()}

    if not squares:
        return f"There are no {colour_str.lower()} {plural[piece_code.lower()]}."

    if len(squares) == 1:
        return f"{colour_str} {singular[piece_code.lower()]} is on {squares[0]}."

    return f"{colour_str} {plural[piece_code.lower()]} are on {', '.join(squares)}."


def describe_file_or_rank(board: chess.Board, spec: str) -> str:
    """Return verbal description of pieces on a file (a-h) or rank (1-8)."""
    spec = spec.strip().lower()
    if not spec or spec not in "abcdefgh12345678":
        return "Invalid file or rank specification."
    pieces_on_line = []
    for sq, pc in board.piece_map().items():
        sq_name = chess.square_name(sq)
        if spec in "abcdefgh" and sq_name[0] == spec:
            pieces_on_line.append((sq_name, pc))
        elif spec in "12345678" and sq_name[1] == spec:
            pieces_on_line.append((sq_name, pc))
    if not pieces_on_line:
        line_str = f"file {spec}" if spec in "abcdefgh" else f"rank {spec}"
        return f"No pieces on {line_str}."
    pieces_on_line.sort(key=lambda t: (t[0][1], t[0][0]))
    parts = []
    for sq_name, pc in pieces_on_line:
        colour = "White" if pc.color == chess.WHITE else "Black"
        piece_name = chess.piece_name(pc.piece_type)
        parts.append(f"{colour} {piece_name} on {sq_name}")
    line_str = f"file {spec}" if spec in "abcdefgh" else f"rank {spec}"
    return f"Pieces on {line_str}: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Notation helpers
# ---------------------------------------------------------------------------

_NATO_FILES = {
    "a": "alpha", "b": "bravo", "c": "charlie", "d": "delta",
    "e": "echo", "f": "foxtrot", "g": "golf", "h": "hotel",
}
_ANNA_FILES = {
    "a": "anna", "b": "bella", "c": "cesar", "d": "david",
    "e": "eva", "f": "felix", "g": "gustav", "h": "hektor",
}


def format_square(square: str, style: str) -> str:
    file = square[0]
    rank = square[1]
    style = style.lower()
    if style in {"uci", "san"}:
        return square
    elif style == "literate":
        return f"{file} {rank}"
    elif style == "nato":
        return f"{_NATO_FILES[file]} {rank}"
    elif style == "anna":
        return f"{_ANNA_FILES.get(file, file)} {rank}"
    return square


def format_piece_on_square(pc: chess.Piece, square: str, style: str) -> str:
    piece_name = chess.piece_name(pc.piece_type)
    square_fmt = format_square(square, style)
    colour = "White" if pc.color == chess.WHITE else "Black"
    return f"{colour} {piece_name} on {square_fmt}"


# ---------------------------------------------------------------------------
# Global Main Menu and Help System
# ---------------------------------------------------------------------------

def show_help(context_name: str):
    """Display help for the current context."""
    help_texts = {
        "main_menu": [
            "1 – Local games list",
            "2 – Live broadcasts",
            "3 – Settings",
            "q – Quit program",
            "b – Back (return to previous)"
        ],
        "game_selection": [
            "<num> – open game", "n – new game", "save – save & back",
            "r – reload PGN", "b – live broadcasts", "m – main menu",
            "b – back (quit)", "h – help"
        ],
        "game_view": [
            "Enter/next – make next main-line move",
            "b/prev – go to previous move",
            "<move> (e4,Nf3 or e2e4) – make a move",
            "p <piece> – list piece locations",
            "s <file|rank> – list pieces on a file or rank",
            "eval/c – Stockfish evaluation", "a – start interactive analysis panel",
            "t – opening tree", "pg – show PGN",
            "save – save & exit", "m – main menu", "h – help"
        ],
        "broadcast_menus": [
            "<num> – select", "r – refresh", "b – back", "m – main menu", "h – help"
        ],
    }
    clear_screen_and_prepare_for_new_content()
    print(f"--- Help: {context_name} ---")
    for line in help_texts.get(context_name, []):
        print(line)
    print("-"*20)
    input("Press Enter to return...")


def show_main_menu(game_manager: GameManager | None, settings_manager: SettingsManager, engine):
    """Global main menu accessible from any context. Returns when user backs out."""
    while True:
        clear_screen_and_prepare_for_new_content()
        print("--- MAIN MENU ---")
        if game_manager is not None:
            print("1. Local games")
        else:
            print("(Local games unavailable in this context)")
        print("2. Live broadcasts")
        print("3. Settings")
        print("q. Quit program")
        print("h. Help  |  b. Back")
        choice = input("Select option: ").strip().lower()
        if choice == "1" and game_manager is not None:
            sel_idx = show_game_selection_menu(game_manager, settings_manager, engine)
            if isinstance(sel_idx, int):
                play_game(game_manager, engine, sel_idx, settings_manager)
        elif choice == "2":
            bc_manager = BroadcastManager()
            bc_manager.fetch_broadcasts()
            res = show_broadcasts_menu(bc_manager)
            if isinstance(res, chess.pgn.Game):
                play_game(
                    game_manager,
                    engine,
                    res,
                    settings_manager,
                    is_broadcast=True,
                    broadcast_id=bc_manager.selected_broadcast["id"],
                    round_id=bc_manager.selected_round["id"],
                    game_id=getattr(res, "game_id", res.headers.get("Site", "").split("/")[-1]),
                )
            # Otherwise (BACK/None), simply continue to show main menu
        elif choice == "3":
            show_settings_menu(settings_manager)
        elif choice == "h":
            show_help("main_menu")
        elif choice in ("b", "q"):
            # 'q' from main menu quits entire program
            if choice == "q":
                sys.exit(0)
            break
        else:
            print("Invalid option.")
            time.sleep(0.7)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    """Launch the classic text CLI."""
    settings_manager = SettingsManager()
    # Engine setup
    engine = None
    try:
        user_cfg_path = settings_manager.get("engine_path") or ""

        # Determine correct binary name for this platform
        sys_plat = sys.platform
        machine = platform.machine().lower()
        bin_name = "stockfish"  # fallback
        if sys_plat.startswith("darwin"):
            if "arm" in machine or "aarch" in machine:
                bin_name = "stockfish"
            else:
                bin_name = "stockfish_x86"
        elif sys_plat.startswith("linux"):
            # provide reasonable defaults; users typically supply their own on Linux
            bin_name = "stockfish"
        elif sys_plat.startswith("win"):
            bin_name = "stockfish.exe"

        default_path = None
        if getattr(sys, "_MEIPASS", None):  # PyInstaller temp dir
            # Try the path used in workflow: engine/<binary>
            cand1 = Path(sys._MEIPASS) / "engine" / bin_name
            cand2 = Path(sys._MEIPASS) / bin_name  # fallback same dir
            default_path = cand1 if cand1.exists() else cand2
        else:
            # Running from source – look inside engine/<platform> folder relative to package root
            pkg_root = Path(__file__).resolve().parent
            cand1 = pkg_root / "engine" / ("mac" if sys_plat.startswith("darwin") else "win") / bin_name
            cand2 = pkg_root / "engine" / bin_name
            default_path = cand1 if cand1.exists() else cand2

        # Pick whichever path is non-empty
        candidate_path = Path(user_cfg_path) if user_cfg_path else default_path

        if candidate_path.exists():
            engine = chess.engine.SimpleEngine.popen_uci(str(candidate_path))
        else:
            print("INFO: Chess engine not found. Configure Engine Path in Settings menu.")
    except Exception as e:
        print(f"Error loading chess engine: {e}")
        time.sleep(2)

    # PGN file setup
    pgn_file_provided = len(sys.argv) > 1 and sys.argv[1].lower().endswith('.pgn')
    if pgn_file_provided:
        # If a PGN file is passed as an argument, use it directly.
        actual_pgn_path = sys.argv[1]
        if not os.path.exists(actual_pgn_path):
            print(f"Error: PGN file not found at {actual_pgn_path}")
            sys.exit(1)
    else:
        # Otherwise, use the default PGN file from settings.
        pgn_dir = settings_manager.get("pgn_file_directory")
        if not os.path.isdir(pgn_dir):
            os.makedirs(pgn_dir, exist_ok=True)
        actual_pgn_path = os.path.join(pgn_dir, settings_manager.get("default_pgn_filename"))

    if not os.path.exists(actual_pgn_path):
        # Create a new empty file with a placeholder game if none exists.
        with open(actual_pgn_path, "w") as f:
            board = chess.Board()
            game = chess.pgn.Game()
            game.setup(board)
            game.headers["Event"] = "New Game"
            f.write(str(game))
        print(f"Created new PGN file at: {actual_pgn_path}")
        time.sleep(1)

    game_manager = GameManager(actual_pgn_path)
    
    clear_screen_and_prepare_for_new_content(is_first_draw=True)
    print("Welcome to Blind-Base CLI!")
    time.sleep(0.5)

    # If no PGN file argument was provided, start with the Main Menu instead of the game list.
    if not pgn_file_provided:
        show_main_menu(game_manager, settings_manager, engine)
        # After the user backs out of the main menu they intend to quit.
        clear_screen_and_prepare_for_new_content()
        print("Quitting engine...")
        if engine:
            engine.quit()
        return

    try:
        # PGN argument supplied – start directly in the game selection loop.
        while True:
            result = show_game_selection_menu(game_manager, settings_manager, engine)

            if result is None:  # User chose to quit from the game selection menu.
                break
            
            elif result == "BROADCAST":
                # User wants to see broadcasts. Enter the broadcast browsing loop.
                broadcast_manager = BroadcastManager()
                broadcast_manager.fetch_broadcasts()
                
                # This inner loop lets the user browse broadcasts, rounds, and games.
                # It only exits when the user selects a game to play or backs out to the top level.
                while True: 
                    selected_game = show_broadcasts_menu(broadcast_manager)
                    if selected_game:
                        # A broadcast game was selected via BROADCAST signal, play it.
                        play_game(
                            game_manager, # Note: passing local game_manager, may not be ideal
                            engine,
                            selected_game,
                            settings_manager,
                            is_broadcast=True,
                            broadcast_id=broadcast_manager.selected_broadcast["id"],
                            round_id=broadcast_manager.selected_round["id"],
                            game_id=getattr(selected_game, "game_id", selected_game.headers.get("Site", "").split("/")[-1]),
                        )
                        # After the game finishes, this loop continues, which will re-show the broadcast list.
                        # This fixes the bug where exiting a game went to the wrong menu.
                    else:
                        # The user backed out of the broadcast menu. We break this inner loop
                        # to return to the main game selection menu.
                        break
            
            else:  # The result is a game index from the local PGN file.
                play_game(game_manager, engine, result, settings_manager)
                # After the game, the main `while` loop continues, which will re-show the local game list.
                # This also fixes the bug of returning to the wrong menu.

    finally:
        # Cleanup before exiting the program.
        clear_screen_and_prepare_for_new_content()
        print("Quitting engine...")
        if engine:
            engine.quit()
        print("Program exited.")


if __name__ == "__main__":
    main()

def describe_piece_locations_formatted(board: chess.Board, piece_code: str, style: str) -> str:
    raw = describe_piece_locations(board, piece_code)
    # replace every square pattern with formatted square if needed when raw contains chess.square strings separated by commas.
    # Simplistic approach: split by space, for each token that is two chars and matches square, replace.
    words = raw.split()
    new_words = []
    for w in words:
        if len(w) >=2 and w[0] in 'abcdefgh' and w[1] in '12345678':
            sq = w.rstrip(',.')
            formatted = format_square(sq, style)
            w = w.replace(sq, formatted)
        elif len(w)>=3 and w[0] in 'KQRBN' and w[1] in 'abcdefgh' and w[2] in '12345678':
            piece_word={'K':'King','Q':'Queen','R':'Rook','B':'Bishop','N':'Knight'}[w[0]]
            sq=w[1:3]
            w=piece_word+' '+format_square(sq,style)
        new_words.append(w)
    return ' '.join(new_words)

def describe_file_or_rank_formatted(board: chess.Board, spec: str, style: str) -> str:
    raw = describe_file_or_rank(board, spec)
    words = raw.split()
    new_w=[]
    for w in words:
        core=w.strip(';,.:')
        if len(core)==2 and core[0] in 'abcdefgh' and core[1] in '12345678':
            formatted = format_square(core, style)
            w = w.replace(core, formatted)
        new_w.append(w)
    return ' '.join(new_w)

def move_to_str(board: chess.Board, move: chess.Move, style: str) -> str:
    """Return a formatted string for a move, given the board context."""
    style = style.lower()
    if style == "uci":
        return move.uci()
    san = board.san(move)
    if style == "san":
        return san

    # Build output progressively
    out = san

    # Square names replacement first
    for sq in {chess.square_name(move.from_square), chess.square_name(move.to_square)}:
        out = out.replace(sq, format_square(sq, style))

    if style in {"literate", "nato", "anna"}:
        piece_map = {"K":"King", "Q":"Queen", "R":"Rook", "B":"Bishop", "N":"Knight"}
        # Leading piece letter to word
        if san[0] in piece_map:
            out = piece_map[san[0]] + " " + out[1:]
        # Capture indicator
        if 'x' in san:
            out = out.replace('x', ' takes ', 1)
        # Collapse multiple spaces
        out = re.sub(r"\s+", " ", out)
    return out.strip() 