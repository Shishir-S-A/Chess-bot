import tkinter as tk
from tkinter import messagebox
import sys
import platform
if platform.system() == "Windows":
    import winsound
else:
    winsound = None
import chess
import chess.engine
from PIL import Image, ImageTk

import threading

# Set this to your Stockfish executable path (portable: always looks in the same folder as the script/exe)
import os
STOCKFISH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockfish-windows-x86-64-avx2.exe")

PIECE_IMAGES = {}
PIECES = ['r', 'n', 'b', 'q', 'k', 'p', 'R', 'N', 'B', 'Q', 'K', 'P']

# Polyglot opening book path
POLYGLOT_BOOK_PATH = r"C:\Users\hp\OneDrive\Desktop\Chess bot\komodo.bin"
import chess.polyglot

class ChessGUI:
    # --- Board themes ---
    BOARD_THEMES = {
        "Classic": ("#F0D9B5", "#B58863"),
        "Blue": ("#aad4ff", "#3a6ea5"),
        "Green": ("#d2ecd2", "#5ca05c"),
        "Gray": ("#e0e0e0", "#888888"),
        "Brown": ("#f5deb3", "#8b5a2b"),
        "Purple": ("#e5d6ff", "#7c4dff"),
        "Pink": ("#ffe0ef", "#e75480"),
        "Orange": ("#ffe5b4", "#ff9900"),
        "Red": ("#ffd6d6", "#c0392b"),
    }

    def play_sound(self, sound_name):
        """Play a sound effect from the sounds/ folder. sound_name: 'move', 'capture', 'check'"""
        import os
        sound_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", f"{sound_name}.wav")
        if not os.path.exists(sound_file):
            # Uncomment the next line to debug missing sound files
            # print(f"[SOUND] File not found: {sound_file}")
            return  # No sound file, skip
        try:
            if winsound:
                # Stop any currently playing sound first (to avoid overlap)
                winsound.PlaySound(None, winsound.SND_PURGE)
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                # On Linux/Mac, try to use aplay/afplay if available
                import subprocess
                if sys.platform == "darwin":
                    subprocess.Popen(["afplay", sound_file])
                else:
                    subprocess.Popen(["aplay", sound_file])
        except Exception as e:
            print(f"[SOUND ERROR] {e}")
    def fen_entry_callback(self, event=None):
        fen = self.fen_var.get().strip()
        import chess
        try:
            board = chess.Board(fen)
            if board.is_valid():
                self.board = board
                self.update_castling_vars_from_board()
                self.draw_board()
                self.calculate_and_show_best_move()
                self.fen_entry.config(bg="#eaffea")  # light green for valid
            else:
                self.fen_entry.config(bg="#ffeaea")  # light red for invalid
        except Exception:
            self.fen_entry.config(bg="#ffeaea")  # light red for invalid
    def start_loading_animation(self):
        self._loading_anim_frames = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
        self._loading_anim_index = 0
        self._loading_anim_running = True
        self._current_depth = None
        self._animate_loading()

    def _animate_loading(self):
        if not getattr(self, '_loading_anim_running', False):
            return
        frame = self._loading_anim_frames[self._loading_anim_index]
        depth_str = f"  Depth: {self._current_depth}" if self._current_depth is not None else ""
        self.status.config(text=f"Calculating best move {frame}{depth_str}", fg="black")
        self._loading_anim_index = (self._loading_anim_index + 1) % len(self._loading_anim_frames)
        self._loading_anim_after_id = self.root.after(100, self._animate_loading)

    def stop_loading_animation(self):
        self._loading_anim_running = False
        if hasattr(self, '_loading_anim_after_id'):
            self.root.after_cancel(self._loading_anim_after_id)
            del self._loading_anim_after_id
    def go_back_one_move(self, event=None):
        if self.board.move_stack:
            self.board.pop()
            self.draw_board()
            self.calculate_and_show_best_move()
    def on_right_click(self, event):
        col, row = event.x // 60, event.y // 60
        if 0 <= col < 8 and 0 <= row < 8:
            self._right_click_start = (col, row, event.x, event.y)
            self.arrow_drag = {'from': (col, row), 'to': (col, row)}
        else:
            self._right_click_start = None
            self.arrow_drag = None

    def on_right_drag(self, event):
        if self.arrow_drag is not None:
            col, row = event.x // 60, event.y // 60
            self.arrow_drag['to'] = (col, row)
            # If drag distance is significant, mark as drag
            if hasattr(self, '_right_click_start') and self._right_click_start is not None:
                sx, sy = self._right_click_start[2], self._right_click_start[3]
                if abs(event.x - sx) > 5 or abs(event.y - sy) > 5:
                    self._right_click_dragged = True
            self.draw_board()

    def on_right_release(self, event):
        # If drag distance is small, treat as click (remove piece)
        if hasattr(self, '_right_click_start') and self._right_click_start is not None:
            col, row, sx, sy = self._right_click_start
            dx = abs(event.x - sx)
            dy = abs(event.y - sy)
            if (dx <= 5 and dy <= 5):
                # Click, not drag: remove piece if present
                if 0 <= col < 8 and 0 <= row < 8:
                    if getattr(self, 'flip', False):
                        board_col = 7 - col
                        board_row = 7 - row
                    else:
                        board_col = col
                        board_row = row
                    square = chess.square(board_col, 7 - board_row)
                    piece = self.board.piece_at(square)
                    if piece:
                        self.board.remove_piece_at(square)
                        self.draw_board()
                        self.calculate_and_show_best_move()
                self.arrow_drag = None
                self._right_click_start = None
                self._right_click_dragged = False
                return
        # Otherwise, treat as drag (draw arrow)
        if self.arrow_drag is not None:
            from_col, from_row = self.arrow_drag['from']
            to_col, to_row = self.arrow_drag['to']
            # Only add/remove arrow if drag distance is significant and within board
            if (0 <= from_col < 8 and 0 <= from_row < 8 and
                0 <= to_col < 8 and 0 <= to_row < 8 and
                (from_col != to_col or from_row != to_row)):
                # Convert to board squares
                if getattr(self, 'flip', False):
                    board_from_col = 7 - from_col
                    board_from_row = 7 - from_row
                    board_to_col = 7 - to_col
                    board_to_row = 7 - to_row
                else:
                    board_from_col = from_col
                    board_from_row = from_row
                    board_to_col = to_col
                    board_to_row = to_row
                from_sq = chess.square(board_from_col, 7 - board_from_row)
                to_sq = chess.square(board_to_col, 7 - board_to_row)
                arrow = (from_sq, to_sq)
                if arrow in self.arrows:
                    self.arrows.remove(arrow)
                else:
                    self.arrows.append(arrow)
            self.arrow_drag = None
        self._right_click_start = None
        self._right_click_dragged = False
        self.draw_board()
    def __init__(self, root):
        self.root = root
        self.root.title("Offline Chess - Next Best Move")
        self.board = chess.Board()
        self.selected = None
        self.squares = {}
        self.images = {}
        # --- FEN Entry ---
        self.fen_var = tk.StringVar()
        fen_frame = tk.Frame(root)
        fen_frame.grid(row=22, column=1, columnspan=2, sticky='ew', pady=(8,2))
        tk.Label(fen_frame, text="FEN:").pack(side='left')
        self.fen_entry = tk.Entry(fen_frame, textvariable=self.fen_var, width=70)
        self.fen_entry.pack(side='left', fill='x', expand=True)
        self.fen_entry.bind('<Return>', self.fen_entry_callback)
        self.fen_entry.bind('<FocusOut>', self.fen_entry_callback)
        self.fen_var.set(self.board.fen())
        # Update FEN entry when board changes
        def update_fen_entry(*args):
            self.fen_var.set(self.board.fen())
            self.fen_entry.config(bg="white")
        self.update_fen_entry = update_fen_entry

        # --- Always keep board and FEN in sync after any manual move or edit ---
        self._sync_fen_after_move = True
        # --- Evaluation bar ---
        self.eval_bar_canvas = tk.Canvas(root, width=30, height=600, bg="#DDD", highlightthickness=0)
        self.eval_bar_canvas.grid(row=0, column=0, rowspan=22, sticky='nsw')

        # --- Scrollable left frame for palettes and board ---
        self.left_canvas = tk.Canvas(root, width=480, height=600)
        self.left_canvas.grid(row=0, column=1, rowspan=22, sticky='ns')
        self.left_scrollbar = tk.Scrollbar(root, orient='vertical', command=self.left_canvas.yview)
        self.left_scrollbar.grid(row=0, column=2, rowspan=22, sticky='nsw')
        self.left_frame = tk.Frame(self.left_canvas)
        self.left_frame.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        )
        self.left_canvas.create_window((0, 0), window=self.left_frame, anchor='nw')
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)

        # Piece palettes above and below the board (now inside left_frame)
        self.top_palette = tk.Canvas(self.left_frame, width=480, height=60, bg="#EEE")
        self.top_palette.grid(row=0, column=0)
        self.canvas = tk.Canvas(self.left_frame, width=480, height=480)
        self.canvas.grid(row=1, column=0)
        self.bottom_palette = tk.Canvas(self.left_frame, width=480, height=60, bg="#EEE")
        self.bottom_palette.grid(row=2, column=0)

        self.load_images()
        self.engine = None

        # Controls (right side)
        self.controls_frame = tk.Frame(root)
        self.controls_frame.grid(row=0, column=3, sticky='nw')

        # Reset Board
        self.reset_btn = tk.Button(self.controls_frame, text="Reset Board", command=self.reset_board)
        self.reset_btn.pack(pady=2, anchor='w')

        # Capture All Pieces (Clear Board)
        self.clear_btn = tk.Button(self.controls_frame, text="Capture All Pieces", command=self.clear_board)
        self.clear_btn.pack(pady=2, anchor='w')

        # Flip Board
        self.flip = False
        self.flip_btn = tk.Button(self.controls_frame, text="Flip Board", command=self.flip_board)
        self.flip_btn.pack(pady=2, anchor='w')

        # Active Color
        self.active_color = tk.StringVar(value='w')
        tk.Label(self.controls_frame, text="Active Color:").pack(anchor='w')
        tk.Radiobutton(self.controls_frame, text="White to move", variable=self.active_color, value='w', command=self.set_active_color).pack(anchor='w')
        tk.Radiobutton(self.controls_frame, text="Black to move", variable=self.active_color, value='b', command=self.set_active_color).pack(anchor='w')

        # Castling Availability
        tk.Label(self.controls_frame, text="Castling Availability:").pack(anchor='w')
        self.castle_wk = tk.BooleanVar(value=True)
        self.castle_wq = tk.BooleanVar(value=True)
        self.castle_bk = tk.BooleanVar(value=True)
        self.castle_bq = tk.BooleanVar(value=True)
        tk.Checkbutton(self.controls_frame, text="White/kingside", variable=self.castle_wk, command=self.set_castling).pack(anchor='w')
        tk.Checkbutton(self.controls_frame, text="White/queenside", variable=self.castle_wq, command=self.set_castling).pack(anchor='w')
        tk.Checkbutton(self.controls_frame, text="Black/kingside", variable=self.castle_bk, command=self.set_castling).pack(anchor='w')
        tk.Checkbutton(self.controls_frame, text="Black/queenside", variable=self.castle_bq, command=self.set_castling).pack(anchor='w')


        # Thinking Time Slider
        tk.Label(self.controls_frame, text="Engine Thinking Time (sec):").pack(anchor='w', pady=(10,0))
        self.think_time = tk.IntVar(value=2)
        self.time_slider = tk.Scale(self.controls_frame, from_=1, to=60, orient=tk.HORIZONTAL, variable=self.think_time, showvalue=True, length=180)
        self.time_slider.pack(anchor='w')

        # Calculate Next Move
        self.calc_btn = tk.Button(self.controls_frame, text="Calculate Next Move", command=self.calculate_and_show_best_move)
        self.calc_btn.pack(pady=8, anchor='w')

        # Status label for best move
        self.status = tk.Label(self.controls_frame, text="", font=("Calibri", 14))
        self.status.pack(anchor='w')
        # Second best move label (smaller font, clickable)
        self.second_move_label = tk.Label(self.controls_frame, text="", font=("Calibri", 10), fg="#666", cursor="hand2")
        self.second_move_label.pack(anchor='w')
        self.second_move_label.bind("<Button-1>", lambda e: None)  # Placeholder, will be set dynamically

        # Points label for each player
        self.points_label = tk.Label(self.controls_frame, text="", font=("Calibri", 12), fg="#333")
        self.points_label.pack(anchor='w')

        # --- Initialization that was misplaced ---
        # --- Arrow drawing state ---
        self.arrows = []  # List of (from_square, to_square)
        self.arrow_drag = None  # {'from': (col, row), 'to': (col, row)}

        # Board theme selection
        # Use a traceable StringVar for theme, set default, and ensure event bindings are set at startup
        self.board_theme_name = tk.StringVar()
        self.board_theme_name.set("Classic")
        theme_frame = tk.Frame(self.controls_frame)
        theme_frame.pack(pady=(8,2), anchor='w')
        tk.Label(theme_frame, text="Board Theme:").pack(side='left')
        self.theme_menu = tk.OptionMenu(theme_frame, self.board_theme_name, *self.BOARD_THEMES.keys(), command=self.on_theme_change)
        self.theme_menu.pack(side='left')

        self.init_engine()
        self.draw_board()
        self.draw_palettes()
        # --- Ensure all event bindings are set at startup, not just on theme change ---
        self.canvas.bind('<ButtonPress-1>', self.on_piece_press)
        self.canvas.bind('<B1-Motion>', self.on_piece_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_piece_release)
        self.canvas.bind('<ButtonPress-3>', self.on_right_click)
        self.canvas.bind('<B3-Motion>', self.on_right_drag)
        self.canvas.bind('<ButtonRelease-3>', self.on_right_release)
        self.root.bind('<Left>', self.go_back_one_move)
        self.canvas.focus_set()
        if not hasattr(self, 'clear_arrows_btn'):
            self.clear_arrows_btn = tk.Button(self.controls_frame, text="Clear Arrows", command=self.clear_arrows)
            self.clear_arrows_btn.pack(pady=2, anchor='w')
        self.root.after(100, self._fen_sync_loop)
        credit = tk.Label(self.root, text="App by Shishir", font=("Arial", 8), fg="#888", bg=self.root.cget('bg'))
        credit.place(relx=1.0, rely=1.0, anchor='se', x=-8, y=-4)

    def on_theme_change(self, *args):
        self.draw_board()
        # Bind mouse events for drag-and-drop piece movement on the board (only once)
        self.canvas.bind('<ButtonPress-1>', self.on_piece_press)
        self.canvas.bind('<B1-Motion>', self.on_piece_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_piece_release)
        self.canvas.bind('<ButtonPress-3>', self.on_right_click)
        self.canvas.bind('<B3-Motion>', self.on_right_drag)
        self.canvas.bind('<ButtonRelease-3>', self.on_right_release)
        # Bind left arrow key to go back one move (only once)
        self.root.bind('<Left>', self.go_back_one_move)
        self.canvas.focus_set()
        # Clear Arrows button (only once)
        if not hasattr(self, 'clear_arrows_btn'):
            self.clear_arrows_btn = tk.Button(self.controls_frame, text="Clear Arrows", command=self.clear_arrows)
            self.clear_arrows_btn.pack(pady=2, anchor='w')
        # Start FEN sync loop
        self.root.after(100, self._fen_sync_loop)

        # --- App credit label ---
        credit = tk.Label(self.root, text="App by Shishir", font=("Arial", 8), fg="#888", bg=self.root.cget('bg'))
        credit.place(relx=1.0, rely=1.0, anchor='se', x=-8, y=-4)

    def _fen_sync_loop(self):
        # Keep FEN entry in sync with board (unless user is editing)
        if self.fen_entry.focus_get() != self.fen_entry:
            self.update_fen_entry()
        self.root.after(500, self._fen_sync_loop)
    def init_engine(self):
        if self.engine is None:
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
            except Exception as e:
                print(f"Failed to start Stockfish engine: {e}")
                self.engine = None
    def reset_board(self):
        self.board.reset()
        self.update_castling_vars_from_board()
        self.draw_board()
        self.calculate_and_show_best_move()
        self.update_fen_entry()

    def clear_board(self):
        # Remove all pieces (including kings) for full custom setup
        self.board.clear()
        self.update_castling_vars_from_board()
        self.draw_board()
        self.calculate_and_show_best_move()
        self.update_fen_entry()
    
        # Decide who starts based on active_color
        if (self.active_color.get() == 'w' and self.board.turn == chess.WHITE) or (self.active_color.get() == 'b' and self.board.turn == chess.BLACK):
            # User to play first
            pass
        else:
            # Engine to play first
            self.root.after(500, self.points_match_engine_move)

        import chess
        import chess.engine
        board_fen = self.board.fen()
        try:
            with self.engine.analysis(chess.Board(board_fen), chess.engine.Limit(time=1), multipv=3) as analysis:
                best_move = None
                best_capture_value = -1
                for info in analysis:
                    if 'pv' in info and info['pv']:
                        move = info['pv'][0]
                        captured = self.board.piece_at(move.to_square)
                        value = self.get_piece_value(captured) if captured else 0
                        if value > best_capture_value:
                            best_capture_value = value
                            best_move = move
                if not best_move:
                    # fallback: pick any legal move
                    best_move = next(iter(self.board.legal_moves))
            captured = self.board.piece_at(best_move.to_square)
            self.board.push(best_move)
            if captured:
                self.points_match_engine_points += self.get_piece_value(captured)
            self.points_match_moves += 1
            self.update_points_match_tally()
            self.draw_board()
            if self.points_match_moves >= self.points_match_max_moves:
                self.end_points_match()
                return
            # User's turn next
        except Exception as e:
            self.status.config(text=f"Engine error: {e}", fg="red")
    def get_piece_value(self, piece):
        if not piece:
            return 0
        values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
        return values.get(piece.piece_type, 0)

    def flip_board(self):
        self.flip = not self.flip
        self.draw_board()
        self.update_fen_entry()

    def get_palette_pieces(self):
        # Returns (top_palette_pieces, bottom_palette_pieces) depending on flip
        if getattr(self, 'flip', False):
            # When flipped, swap palettes
            return (
                ['Q', 'R', 'B', 'N', 'P', 'K'],  # white pieces on top
                ['q', 'r', 'b', 'n', 'p', 'k']   # black pieces on bottom
            )
        else:
            return (
                ['q', 'r', 'b', 'n', 'p', 'k'],  # black pieces on top
                ['Q', 'R', 'B', 'N', 'P', 'K']   # white pieces on bottom
            )

    def set_active_color(self):
        self.board.turn = (self.active_color.get() == 'w')
        self.draw_board()
        self.calculate_and_show_best_move()
        self.update_fen_entry()

    def set_castling(self):
        # Set castling rights based on checkboxes
        self.board.clear_stack()
        self.board.castling_rights = 0
        if self.castle_wk.get(): self.board.castling_rights |= chess.BB_H1
        if self.castle_wq.get(): self.board.castling_rights |= chess.BB_A1
        if self.castle_bk.get(): self.board.castling_rights |= chess.BB_H8
        if self.castle_bq.get(): self.board.castling_rights |= chess.BB_A8
        self.draw_board()
        self.calculate_and_show_best_move()
        self.update_fen_entry()

    def update_castling_vars_from_board(self):
        self.castle_wk.set(self.board.has_kingside_castling_rights(chess.WHITE))
        self.castle_wq.set(self.board.has_queenside_castling_rights(chess.WHITE))
        self.castle_bk.set(self.board.has_kingside_castling_rights(chess.BLACK))
        self.castle_bq.set(self.board.has_queenside_castling_rights(chess.BLACK))

    def calculate_and_show_best_move(self):
        # Clear all arrows when calculating next move
        self.clear_arrows()
        self.best_move_arrow = None  # For translucent best move arrow
        # Remove all Points Mode logic and references to self.points_mode
        # (Points Mode is deprecated; Points Match is the new mode)
        # ...proceed to normal engine mode...
        # --- Normal engine mode ---
        self.init_engine()
        if not self.engine:
            self.status.config(text="Engine not available.", fg="red")
            self.status.unbind("<Button-1>")
            self.update_eval_bar(None)
            return
        # Enhanced legality checks for custom positions
        try:
            # --- Block engine analysis if user tries to calculate for the wrong side in check ---
            user_color = self.active_color.get()
            # If white is in check and user tries to analyze for black
            if self.board.king(chess.WHITE) is not None and self.board.king(chess.BLACK) is not None:
                if self.board.is_check() and self.board.turn == chess.WHITE and user_color == 'b':
                    self.status.config(text="White in check!", fg="red")
                    self.status.unbind("<Button-1>")
                    self.update_eval_bar(None)
                    return
                # If black is in check and user tries to analyze for white
                if self.board.is_check() and self.board.turn == chess.BLACK and user_color == 'w':
                    self.status.config(text="Black in check!", fg="red")
                    self.status.unbind("<Button-1>")
                    self.update_eval_bar(None)
                    return
            if not self.board.is_valid():
                # More specific error reporting in terminal
                print("[ERROR] Board is not valid. Possible reasons:")
                if self.board.king(chess.WHITE) is None:
                    print("- Missing white king.")
                if self.board.king(chess.BLACK) is None:
                    print("- Missing black king.")
                if self.board.is_check():
                    print("- One or both kings are in check.")
                print("- There may be other illegalities (e.g., too many pawns, both kings in check, etc.)")
                self.status.config(text="Position is illegal!", fg="red")
                self.status.unbind("<Button-1>")
                self.update_eval_bar(None)
                return
            if self.board.king(chess.WHITE) is None or self.board.king(chess.BLACK) is None:
                print("[ERROR] Missing king(s) on the board.")
                self.status.config(text="Missing king(s)!", fg="red")
                self.status.unbind("<Button-1>")
                self.update_eval_bar(None)
                return
            if self.board.is_checkmate():
                winner = "Black wins" if self.board.turn == chess.WHITE else "White wins"
                self.status.config(text=winner, fg="green")
                self.status.unbind("<Button-1>")
                self.update_eval_bar(None)
                return
            if self.board.is_stalemate():
                self.status.config(text="Stalemate", fg="gold")
                self.status.unbind("<Button-1>")
                self.update_eval_bar(None)
                return
            if not any(self.board.legal_moves):
                print("[ERROR] No legal moves for the current side to move.")
                self.status.config(text="No legal moves for the current side to move!", fg="red")
                self.status.unbind("<Button-1>")
                self.update_eval_bar(None)
                return
        except Exception as ex:
            print(f"[ERROR] Exception during legality check: {ex}")
            self.status.config(text="Position is not legal for engine analysis!", fg="red")
            self.status.unbind("<Button-1>")
            self.update_eval_bar(None)
            return
        self._current_depth = None
        self.status.config(text="Calculating best move", fg="black")
        self.status.unbind("<Button-1>")
        self.update_eval_bar(None)
        self.start_loading_animation()
        def analyse_in_thread(board_fen, think_time):
            try:
                import chess
                board = chess.Board(board_fen)
                multipv_infos = {}
                # Use analysis context manager for live info
                with self.engine.analysis(board, chess.engine.Limit(time=think_time), multipv=2) as analysis:
                    for info in analysis:
                        if info.get('depth') is not None:
                            self._current_depth = info['depth']
                        # Collect by multipv number if present
                        if 'multipv' in info and info.get('pv'):
                            multipv_infos[info['multipv']] = info.copy()
                # After analysis, get the best and second best moves from multipv_infos
                best_move = None
                second_move = None
                best_move_san = None
                second_move_san = None
                result = None
                # multipv=1 is best, multipv=2 is second best
                if 1 in multipv_infos:
                    info1 = multipv_infos[1]
                    result = info1
                    if info1.get('pv'):
                        best_move = info1['pv'][0]
                        best_move_san = board.san(best_move)
                if 2 in multipv_infos:
                    info2 = multipv_infos[2]
                    if info2.get('pv'):
                        second_move = info2['pv'][0]
                        second_move_san = board.san(second_move)
                def update():
                    self.stop_loading_animation()
                    depth_str = f"  Depth: {self._current_depth}" if self._current_depth is not None else ""
                    if best_move_san:
                        self.status.config(text=f"Best move: {best_move_san}{depth_str}", fg="blue")
                        self.status.bind("<Button-1>", lambda e: self.play_best_move(best_move))
                        # Show translucent arrow for best move
                        from_sq = best_move.from_square
                        to_sq = best_move.to_square
                        self.best_move_arrow = (from_sq, to_sq)
                    else:
                        self.status.config(text="No best move found.", fg="red")
                        self.status.unbind("<Button-1>")
                        self.best_move_arrow = None
                    # Show second best move below, smaller font, and make it clickable
                    if second_move_san:
                        self.second_move_label.config(text=f"Second best: {second_move_san}")
                        self.second_move_label.bind("<Button-1>", lambda e, m=second_move: self.play_best_move(m))
                    else:
                        self.second_move_label.config(text="")
                        self.second_move_label.unbind("<Button-1>")
                    self.update_eval_bar(result)
                    self.draw_board()  # Redraw to show best move arrow
                self.root.after(0, update)
            except Exception as e:
                def update():
                    self.stop_loading_animation()
                    self.status.config(text="No best move found.", fg="red")
                    self.status.unbind("<Button-1>")
                    self.second_move_label.config(text="")
                    self.update_eval_bar(None)
                self.root.after(0, update)
        think_time = self.think_time.get() if hasattr(self, 'think_time') else 2
        threading.Thread(target=analyse_in_thread, args=(self.board.fen(), think_time), daemon=True).start()

    def update_eval_bar(self, engine_result):
        '''Draws a chess.com-style evaluation bar on self.eval_bar_canvas, using the current board theme colors.'''
        self.eval_bar_canvas.delete("all")
        bar_height = 480
        bar_top = 60
        bar_left = 5
        bar_width = 20

        # Get current board theme colors
        theme = self.BOARD_THEMES.get(self.board_theme_name.get(), ("#F0D9B5", "#B58863"))
        color_light = theme[0]
        color_dark = theme[1]

        # For mate/advantage highlight, use a strong color that fits the theme
        # We'll use the dark color for white advantage, light color for black advantage, but also overlay a tint for clarity
        # You can customize these for each theme if desired
        color_white_adv = color_dark  # Top (white advantage)
        color_black_adv = color_light  # Bottom (black advantage)

        # Overlay highlight colors for mate (try to keep them visible on all themes)
        color_mate_white = "#6FCF97"  # greenish for white mate
        color_mate_black = "#EB5757"  # reddish for black mate

        # Default: gray bar (no eval)
        if not engine_result or 'score' not in engine_result:
            self.eval_bar_canvas.create_rectangle(bar_left, bar_top, bar_left+bar_width, bar_top+bar_height, fill="#BBB", outline="#AAA")
            self.eval_bar_canvas.create_text(bar_left+bar_width//2, bar_top+bar_height//2, text="?", font=("Arial", 16))
            return
        score = engine_result['score'].white()
        # Handle mate scores
        if score.is_mate():
            mate_in = score.mate()
            if mate_in is not None:
                if mate_in > 0:
                    # White mates: full green bar (mate for white)
                    self.eval_bar_canvas.create_rectangle(bar_left, bar_top, bar_left+bar_width, bar_top+bar_height, fill=color_mate_white, outline="#AAA")
                    self.eval_bar_canvas.create_text(bar_left+bar_width//2, bar_top+20, text=f"M{mate_in}", font=("Arial", 12), fill="#000")
                else:
                    # Black mates: full red bar (mate for black)
                    self.eval_bar_canvas.create_rectangle(bar_left, bar_top, bar_left+bar_width, bar_top+bar_height, fill=color_mate_black, outline="#AAA")
                    self.eval_bar_canvas.create_text(bar_left+bar_width//2, bar_top+bar_height-20, text=f"M{abs(mate_in)}", font=("Arial", 12), fill="#FFF")
            return
        # Centipawn score: map to bar
        try:
            cp = score.score()
        except Exception:
            cp = 0
        # Clamp evaluation to [-10, +10] pawns
        cp = max(-1000, min(1000, cp))
        # 0 = center, +1000 = all white, -1000 = all black
        # White at top, black at bottom
        white_height = int(bar_height * (1000 - cp) / 2000)
        black_height = bar_height - white_height
        # Draw white part (top)
        self.eval_bar_canvas.create_rectangle(bar_left, bar_top, bar_left+bar_width, bar_top+white_height, fill=color_white_adv, outline="#AAA")
        # Draw black part (bottom)
        self.eval_bar_canvas.create_rectangle(bar_left, bar_top+white_height, bar_left+bar_width, bar_top+bar_height, fill=color_black_adv, outline="#AAA")
        # Draw a highlight if the eval is very high/low
        if cp >= 900:
            # Almost winning for white
            self.eval_bar_canvas.create_rectangle(bar_left, bar_top, bar_left+bar_width, bar_top+bar_height, fill=color_mate_white, outline="#AAA")
            self.eval_bar_canvas.create_text(bar_left+bar_width//2, bar_top+20, text=f"+{cp//100}", font=("Arial", 12), fill="#000")
        elif cp <= -900:
            # Almost winning for black
            self.eval_bar_canvas.create_rectangle(bar_left, bar_top, bar_left+bar_width, bar_top+bar_height, fill=color_mate_black, outline="#AAA")
            self.eval_bar_canvas.create_text(bar_left+bar_width//2, bar_top+bar_height-20, text=f"{cp//100}", font=("Arial", 12), fill="#FFF")
        else:
            # Draw score text in the middle
            score_str = f"{cp/100:.2f}"
            y_pos = bar_top+white_height-10 if white_height > 30 and white_height < bar_height-30 else (bar_top+bar_height//2)
            self.eval_bar_canvas.create_text(bar_left+bar_width//2, y_pos, text=score_str, font=("Arial", 10), fill="#000")

    def play_best_move(self, move):
        # Play the move if legal, then force turn to selected color (for custom play)
        if move in self.board.legal_moves:
            # Clear all arrows (user and best move) before making the move
            self.arrows.clear()
            self.best_move_arrow = None
            captured = self.board.piece_at(move.to_square)
            # Detect castling before making the move
            is_castle = False
            piece = self.board.piece_at(move.from_square)
            if piece and piece.piece_type == chess.KING:
                if abs(chess.square_file(move.from_square) - chess.square_file(move.to_square)) == 2:
                    is_castle = True
            self.board.push(move)
            # Play sound: castle, check, capture, or move
            if is_castle:
                self.play_sound('castle')
            elif self.board.is_check():
                self.play_sound('check')
            elif captured:
                self.play_sound('capture')
            else:
                self.play_sound('move')
            # Force turn to selected color for custom play
            self.board.turn = (self.active_color.get() == 'w')
            self.draw_board()
            self.calculate_and_show_best_move()
            self.update_fen_entry()
        else:
            self.status.config(text="Move not legal for current side to move!", fg="red")
            self.status.unbind("<Button-1>")

    def load_images(self):
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        pieces_dir = os.path.join(script_dir, "pieces")
        print(f"Script directory: {script_dir}")
        print(f"Pieces directory: {pieces_dir}")
        for piece in PIECES:
            if piece.isupper():
                filename = f"w{piece.upper()}.png"  # White pieces
            else:
                filename = f"b{piece.upper()}.png"  # Black pieces
            path = os.path.join(pieces_dir, filename)
            print(f"Loading: {path}")  # Debug print
            try:
                img = Image.open(path).resize((60, 60), Image.LANCZOS)
                PIECE_IMAGES[piece] = ImageTk.PhotoImage(img)
            except FileNotFoundError:
                print(f"ERROR: Could not find image file: {path}")
                PIECE_IMAGES[piece] = None

    def draw_board(self, dragging_piece=None, dragging_pos=None):
        # Use selected theme
        theme = self.BOARD_THEMES.get(self.board_theme_name.get(), ("#F0D9B5", "#B58863"))
        colors = [theme[0], theme[1]]
        self.canvas.delete("all")
        # Draw squares and pieces
        for row in range(8):
            for col in range(8):
                draw_col = 7 - col if getattr(self, 'flip', False) else col
                draw_row = 7 - row if getattr(self, 'flip', False) else row
                x1, y1 = draw_col*60, draw_row*60
                x2, y2 = x1+60, y1+60
                color = colors[((row+col)%2)]
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, tags="square")
                square = chess.square(col, 7-row)
                piece = self.board.piece_at(square)
                if piece:
                    if dragging_piece and dragging_piece['square'] == square:
                        continue
                    img = PIECE_IMAGES[piece.symbol()]
                    self.canvas.create_image(x1+30, y1+30, image=img, tags="piece")
        # Draw the dragged piece on top, following the mouse
        if dragging_piece and dragging_pos:
            img = PIECE_IMAGES[dragging_piece['piece'].symbol()]
            self.canvas.create_image(dragging_pos[0], dragging_pos[1], image=img, tags="dragged_piece")

        # Draw arrows
        def square_center(col, row):
            return col*60+30, row*60+30
        # Draw user arrows
        for from_sq, to_sq in self.arrows:
            from_col, from_row = chess.square_file(from_sq), 7 - chess.square_rank(from_sq)
            to_col, to_row = chess.square_file(to_sq), 7 - chess.square_rank(to_sq)
            if getattr(self, 'flip', False):
                from_col, from_row = 7 - from_col, 7 - from_row
                to_col, to_row = 7 - to_col, 7 - to_row
            x1, y1 = square_center(from_col, from_row)
            x2, y2 = square_center(to_col, to_row)
            self._draw_arrow(x1, y1, x2, y2, color="#2600ff", width=5)
        # Draw best move thin light arrow if present
        if hasattr(self, 'best_move_arrow') and self.best_move_arrow:
            from_sq, to_sq = self.best_move_arrow
            from_col, from_row = chess.square_file(from_sq), 7 - chess.square_rank(from_sq)
            to_col, to_row = chess.square_file(to_sq), 7 - chess.square_rank(to_sq)
            if getattr(self, 'flip', False):
                from_col, from_row = 7 - from_col, 7 - from_row
                to_col, to_row = 7 - to_col, 7 - to_row
            x1, y1 = square_center(from_col, from_row)
            x2, y2 = square_center(to_col, to_row)
            # Draw a thin, light blue arrow (no dash)
            self._draw_arrow(x1, y1, x2, y2, color="#99ccff", width=5)
        # Draw arrow being dragged
        if self.arrow_drag is not None:
            x1, y1 = square_center(*self.arrow_drag['from'])
            x2, y2 = square_center(*self.arrow_drag['to'])
            self._draw_arrow(x1, y1, x2, y2, color="#1100ff", width=3, dash=(4,2))

        # Draw rank (1-8) and file (a-h) labels
        files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        if getattr(self, 'flip', False):
            files = files[::-1]
            ranks = ['1', '2', '3', '4', '5', '6', '7', '8']
        else:
            ranks = ['8', '7', '6', '5', '4', '3', '2', '1']
        # Files (a-h) below the board
        for i, file_char in enumerate(files):
            self.canvas.create_text(i*60+30, 480-8, text=file_char, font=("Arial", 10), fill="#444")
        # Ranks (1-8) left of the board
        for i, rank_char in enumerate(ranks):
            self.canvas.create_text(8, i*60+30, text=rank_char, font=("Arial", 10), fill="#444")

        self.update_points_label()
        self.root.update_idletasks()
        self.draw_palettes()

        # --- Always update FEN entry after any board change ---
        if getattr(self, '_sync_fen_after_move', False):
            self.update_fen_entry()

    def _draw_arrow(self, x1, y1, x2, y2, color="#1201ff", width=5, dash=None):
        # If the arrow is a knight move, draw an L-shaped arrow
        def is_knight_move(x1, y1, x2, y2):
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            # Each square is 60x60, so knight moves are (1,2) or (2,1) squares
            return (dx == 60 and dy == 120) or (dx == 120 and dy == 60)

        if is_knight_move(x1, y1, x2, y2):
            # Draw an L-shaped arrow for knight moves
            # Determine the intermediate corner point
            if abs(x2 - x1) == 60:
                # Horizontal first, then vertical
                mid_x = x2
                mid_y = y1
            else:
                # Vertical first, then horizontal
                mid_x = x1
                mid_y = y2
            # Draw two segments: start to corner, corner to end
            self.canvas.create_line(x1, y1, mid_x, mid_y, fill=color, width=width, capstyle=tk.ROUND, dash=dash)
            self.canvas.create_line(mid_x, mid_y, x2, y2, fill=color, width=width, arrow=tk.LAST, arrowshape=(16,20,6), capstyle=tk.ROUND, dash=dash)
        else:
            # Draw main line for non-knight moves
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width, arrow=tk.LAST, arrowshape=(16,20,6), capstyle=tk.ROUND, dash=dash)

    def clear_arrows(self):
        self.arrows.clear()
        self.draw_board()

    def update_points_label(self):
        # Standard chess piece values
        piece_values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9
        }
        # Starting counts for each piece type
        starting_counts = {
            chess.PAWN: 8,
            chess.KNIGHT: 2,
            chess.BISHOP: 2,
            chess.ROOK: 2,
            chess.QUEEN: 1
        }
        # Count current pieces
        white_counts = {pt: 0 for pt in piece_values}
        black_counts = {pt: 0 for pt in piece_values}
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.piece_type in piece_values:
                if piece.color == chess.WHITE:
                    white_counts[piece.piece_type] += 1
                else:
                    black_counts[piece.piece_type] += 1
        # Calculate material for each side
        white_material = 0
        black_material = 0
        for pt in piece_values:
            white_material += white_counts[pt] * piece_values[pt]
            black_material += black_counts[pt] * piece_values[pt]
        # Material advantage: positive means White is ahead, negative means Black is ahead
        advantage = white_material - black_material
        if advantage > 0:
            text = f"Material: White +{advantage}"
        elif advantage < 0:
            text = f"Material: Black +{-advantage}"
        else:
            text = "Material: Equal"
        self.points_label.config(text=text)

    def on_piece_press(self, event):
        col, row = event.x // 60, event.y // 60
        # Adjust for flip
        if getattr(self, 'flip', False):
            board_col = 7 - col
            board_row = 7 - row
        else:
            board_col = col
            board_row = row
        square = chess.square(board_col, 7 - board_row)
        piece = self.board.piece_at(square)
        # Allow dragging any piece, regardless of side to move or active color
        if piece:
            self.drag_data = {
                'piece': piece,
                'square': square,
                'start_xy': (event.x, event.y),
                'dragging': True
            }
        else:
            self.drag_data = None

    def on_piece_drag(self, event):
        if hasattr(self, 'drag_data') and self.drag_data and self.drag_data.get('dragging'):
            self.draw_board(dragging_piece=self.drag_data, dragging_pos=(event.x, event.y))

    def on_piece_release(self, event):
        if not hasattr(self, 'drag_data') or not self.drag_data or not self.drag_data.get('dragging'):
            return
        from_square = self.drag_data['square']
        to_col, to_row = event.x // 60, event.y // 60
        if getattr(self, 'flip', False):
            board_col = 7 - to_col
            board_row = 7 - to_row
        else:
            board_col = to_col
            board_row = to_row
        # If released outside the board, remove the piece
        if not (0 <= to_col < 8 and 0 <= to_row < 8):
            self.board.remove_piece_at(from_square)
            self.draw_board()
            self.calculate_and_show_best_move()
            self.play_sound('move')
            self.drag_data = None
            self.update_fen_entry()  # Always sync FEN after manual edit
            return
        to_square = chess.square(board_col, 7 - board_row)
        # Allow moving any piece to any square (custom setup style)
        # If a piece exists at the destination, replace it
        moving_piece = self.drag_data['piece']
        captured = self.board.piece_at(to_square)
        self.board.remove_piece_at(to_square)
        self.board.remove_piece_at(from_square)
        self.board.set_piece_at(to_square, moving_piece)
        self.draw_board()
        self.calculate_and_show_best_move()
        # Play sound: check, capture, or move
        if self.board.is_check():
            self.play_sound('check')
        elif captured:
            self.play_sound('capture')
        else:
            self.play_sound('move')
        self.drag_data = None
        self.update_fen_entry()  # Always sync FEN after manual edit

    def update_best_move(self):
        import threading
        if not self.engine:
            self.status.config(text="Engine not available.")
            return
        # Enhanced legality checks for custom positions
        try:
            if not self.board.is_valid():
                self.status.config(text="Position is illegal!", fg="red")
                self.status.unbind("<Button-1>")
                return
            if self.board.king(chess.WHITE) is None or self.board.king(chess.BLACK) is None:
                self.status.config(text="Missing king(s)!", fg="red")
                self.status.unbind("<Button-1>")
                return
            if self.board.is_checkmate():
                winner = "Black wins" if self.board.turn == chess.WHITE else "White wins"
                self.status.config(text=winner, fg="green")
                self.status.unbind("<Button-1>")
                return
            if self.board.is_stalemate():
                self.status.config(text="Stalemate", fg="gold")
                self.status.unbind("<Button-1>")
                return
            if not any(self.board.legal_moves):
                self.status.config(text="No legal moves for the current side to move!", fg="red")
                self.status.unbind("<Button-1>")
                return
        except Exception:
            self.status.config(text="Position is not legal for engine analysis!", fg="red")
            self.status.unbind("<Button-1>")
            return
        self.status.config(text="Calculating best move", fg="black")
        self.status.unbind("<Button-1>")
        def analyse_in_thread(board_fen):
            try:
                import chess
                board = chess.Board(board_fen)
                result = self.engine.analyse(board, chess.engine.Limit(time=0.5))
                move = result['pv'][0]
                move_san = board.san(move)
                def update():
                    self.status.config(text=f"Best move: {move_san}", fg="blue")
                    self.status.bind("<Button-1>", lambda e: self.play_best_move(move))
                self.root.after(0, update)
            except Exception as e:
                def update():
                    self.status.config(text="No best move found.", fg="red")
                    self.status.unbind("<Button-1>")
                self.root.after(0, update)
        threading.Thread(target=analyse_in_thread, args=(self.board.fen(),), daemon=True).start()

    def on_closing(self):
        if hasattr(self, 'engine') and self.engine:
            try:
                self.engine.quit()
            except Exception:
                pass
        self.root.destroy()

    def draw_palettes(self):
        # Draw palettes according to board orientation
        top_pieces, bottom_pieces = self.get_palette_pieces()
        self.top_palette.delete("all")
        for i, piece in enumerate(top_pieces):
            img = PIECE_IMAGES[piece]
            self.top_palette.create_image(i*80+40, 30, image=img, tags=(f"top_{piece}", "palette_piece"))
        self.bottom_palette.delete("all")
        for i, piece in enumerate(bottom_pieces):
            img = PIECE_IMAGES[piece]
            self.bottom_palette.create_image(i*80+40, 30, image=img, tags=(f"bottom_{piece}", "palette_piece"))
        # Bind palette events for drag and drop
        self.top_palette.bind('<ButtonPress-1>', self.on_palette_press)
        self.top_palette.bind('<B1-Motion>', self.on_palette_drag)
        self.top_palette.bind('<ButtonRelease-1>', self.on_palette_release)
        self.bottom_palette.bind('<ButtonPress-1>', self.on_palette_press)
        self.bottom_palette.bind('<B1-Motion>', self.on_palette_drag)
        self.bottom_palette.bind('<ButtonRelease-1>', self.on_palette_release)

    def on_palette_press(self, event):
        # Determine which palette and which piece was clicked, respecting flip
        widget = event.widget
        x = event.x
        y = event.y
        top_pieces, bottom_pieces = self.get_palette_pieces()
        if widget == self.top_palette:
            palette = 'top'
            pieces = top_pieces
        else:
            palette = 'bottom'
            pieces = bottom_pieces
        idx = x // 80
        if 0 <= idx < 6:
            piece = pieces[idx]
            self.palette_drag_data = {
                'piece': piece,
                'palette': palette,
                'start_xy': (x, y),
                'dragging': True,
                'widget': widget
            }
        else:
            self.palette_drag_data = None

    def on_palette_drag(self, event):
        # Optional: implement visual feedback for dragging
        pass

    def on_palette_release(self, event):
        if not hasattr(self, 'palette_drag_data') or not self.palette_drag_data or not self.palette_drag_data.get('dragging'):
            return
        # Get drop location on the main board
        widget = event.widget
        # Only allow drop if mouse is over the main board
        board_x = self.canvas.winfo_rootx()
        board_y = self.canvas.winfo_rooty()
        mouse_x = event.x_root
        mouse_y = event.y_root
        rel_x = mouse_x - board_x
        rel_y = mouse_y - board_y
        if 0 <= rel_x < 480 and 0 <= rel_y < 480:
            col = int(rel_x // 60)
            row = int(rel_y // 60)
            # Adjust for flip
            if getattr(self, 'flip', False):
                board_col = 7 - col
                board_row = 7 - row
            else:
                board_col = col
                board_row = row
            square = chess.square(board_col, 7 - board_row)
            # Place the piece on the board
            self.board.remove_piece_at(square)
            self.board.set_piece_at(square, chess.Piece.from_symbol(self.palette_drag_data['piece']))
            self.draw_board()
            self.calculate_and_show_best_move()
        self.palette_drag_data = None

    def draw_palettes(self):
        # Draw palettes according to board orientation using get_palette_pieces()
        top_pieces, bottom_pieces = self.get_palette_pieces()
        self.top_palette.delete("all")
        for i, piece in enumerate(top_pieces):
            img = PIECE_IMAGES[piece]
            self.top_palette.create_image(i*80+40, 30, image=img, tags=(f"top_{piece}", "palette_piece"))
        self.bottom_palette.delete("all")
        for i, piece in enumerate(bottom_pieces):
            img = PIECE_IMAGES[piece]
            self.bottom_palette.create_image(i*80+40, 30, image=img, tags=(f"bottom_{piece}", "palette_piece"))
        # Bind palette events for drag and drop
        self.top_palette.bind('<ButtonPress-1>', self.on_palette_press)
        self.top_palette.bind('<B1-Motion>', self.on_palette_drag)
        self.top_palette.bind('<ButtonRelease-1>', self.on_palette_release)
        self.bottom_palette.bind('<ButtonPress-1>', self.on_palette_press)
        self.bottom_palette.bind('<B1-Motion>', self.on_palette_drag)
        self.bottom_palette.bind('<ButtonRelease-1>', self.on_palette_release)

if __name__ == "__main__":
    root = tk.Tk()
    app = ChessGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
