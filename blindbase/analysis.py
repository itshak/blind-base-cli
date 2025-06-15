from __future__ import annotations

import shutil
import sys
import time
from typing import List

import chess
import chess.engine


__all__ = [
    "get_analysis_block_height",
    "clear_analysis_block_dynamic",
    "print_analysis_refined",
    "analysis_thread_refined",
]


# ----------------------------------------------------------------------
# Utilities copied from the original script
# ----------------------------------------------------------------------

def get_analysis_block_height(settings_manager) -> int:
    num_engine_lines = settings_manager.get("engine_lines_count")
    padding = settings_manager.get("analysis_block_padding")
    return 2 + num_engine_lines + padding


def clear_analysis_block_dynamic(settings_manager):
    block_height = get_analysis_block_height(settings_manager)
    sys.stdout.write(f"\033[{block_height}A")
    for _ in range(block_height):
        sys.stdout.write("\033[2K\n")
    sys.stdout.write(f"\033[{block_height}A")
    sys.stdout.flush()


def print_analysis_refined(depth: int, lines_data: List[str], settings_manager, engine_name: str = "Engine"):
    num_engine_display_lines = settings_manager.get("engine_lines_count")
    block_height = get_analysis_block_height(settings_manager)
    try:
        terminal_width = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        terminal_width = 80
    sys.stdout.write(f"\033[{block_height}A")
    sys.stdout.write("\033[2K" + engine_name[:terminal_width] + "\n")
    depth_text = f"Depth: {depth}"
    sys.stdout.write("\033[2K" + depth_text[:terminal_width] + "\n")
    for i in range(num_engine_display_lines):
        line_prefix = f"Line {i + 1}: "
        content = lines_data[i] if i < len(lines_data) and lines_data[i] else "..."
        full_line_text = line_prefix + content
        line_to_print = (
            full_line_text[: terminal_width - 3] + "..."
            if len(full_line_text) > terminal_width
            else full_line_text
        )
        sys.stdout.write("\033[2K" + line_to_print + "\n")
    remaining_lines_to_fill = block_height - (2 + num_engine_display_lines)
    for _ in range(remaining_lines_to_fill):
        sys.stdout.write("\033[2K\n")
    sys.stdout.flush()


# ----------------------------------------------------------------------
# Engine analysis thread helper
# ----------------------------------------------------------------------

def analysis_thread_refined(engine: chess.engine.SimpleEngine, board: chess.Board, stop_event, settings_manager, shared_pv: dict | None = None):
    num_engine_lines = settings_manager.get("engine_lines_count")
    displayed_depth = 0
    displayed_lines_content = ["..."] * num_engine_lines
    latest_data_at_max_depth = {i: "" for i in range(1, num_engine_lines + 1)}
    max_depth_from_engine_info = 0
    last_display_update_time = time.time()
    engine_name = engine.id.get('name', 'Engine') if hasattr(engine, 'id') else 'Engine'
    print_analysis_refined(displayed_depth, displayed_lines_content, settings_manager, engine_name)
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
                    if shared_pv is not None and pv:
                        shared_pv[multipv_num] = pv[0]
                    if score.is_mate():
                        mate_in_plies = score.pov(chess.WHITE).mate()
                        evaluation = (
                            f"M{abs(mate_in_plies)}" if mate_in_plies is not None else "Mate"
                        )
                    else:
                        cp_score = score.pov(chess.WHITE).score(mate_score=10000)
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
                                potential_new_lines[i - 1] = latest_data_at_max_depth[i]
                        if potential_new_lines != displayed_lines_content or new_depth_to_show != displayed_depth:
                            should_update_display_flag = True
                elif max_depth_from_engine_info == displayed_depth:
                    changed_at_current_depth = False
                    for i in range(1, num_engine_lines + 1):
                        if latest_data_at_max_depth.get(i) and latest_data_at_max_depth[i] != potential_new_lines[i - 1]:
                            potential_new_lines[i - 1] = latest_data_at_max_depth[i]
                            changed_at_current_depth = True
                    if changed_at_current_depth:
                        should_update_display_flag = True
                if should_update_display_flag:
                    new_lines_to_show = potential_new_lines
                    current_time = time.time()
                    if current_time - last_display_update_time > 0.15:
                        engine_name = engine.id.get('name', 'Engine') if hasattr(engine, 'id') else 'Engine'
                        print_analysis_refined(new_depth_to_show, new_lines_to_show, settings_manager, engine_name)
                        displayed_depth = new_depth_to_show
                        displayed_lines_content = new_lines_to_show[:]
                        last_display_update_time = current_time
                time.sleep(0.01)
    except chess.engine.EngineTerminatedError:
        clear_analysis_block_dynamic(settings_manager)
        sys.stdout.write("\033[2KEngine terminated unexpectedly.\n")
        for _ in range(get_analysis_block_height(settings_manager) - 1):
            sys.stdout.write("\033[2K\n")
        sys.stdout.flush()
    except Exception as e:
        clear_analysis_block_dynamic(settings_manager)
        error_message = f"Analysis thread error: {str(e)[:80]}"
        sys.stdout.write(f"\033[2K{error_message}\n")
        for _ in range(get_analysis_block_height(settings_manager) - 1):
            sys.stdout.write("\033[2K\n")
        sys.stdout.flush() 