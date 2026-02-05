import tkinter as tk
import pygame 
import socket
import threading
import json
import random
from PIL import Image, ImageTk
from tkinter import messagebox
import time
import os

# ============= Network Configuration =============
HOST = '192.168.251.73'  # Server host address
PORT = 5555         # Server port number

# ============= Game Constants =============
TILE_SIZE = 30      # Size of each block in pixels
COLUMNS = 10        # Game board width
ROWS = 20          # Game board height

# ============= Local Storage Files =============
SCORES_FILE = "playerscore.json"
LEADERBOARD_FILE = "leader_board.json"

# ============= Score History Linked List =============
class Node:
    def __init__(self, value, timestamp):
        self.value = value
        self.timestamp = timestamp
        self.next = None

class LinkedList:
    def __init__(self):
        self.head = None

    def insert(self, value, timestamp):
        new = Node(value, timestamp)
        new.next = self.head  # link to the previous head
        self.head = new       # new node becomes the head

    def to_list(self):
        """Convert linked list to list of dictionaries for JSON storage"""
        result = []
        current = self.head
        while current:
            result.append({
                "score": current.value,
                "timestamp": current.timestamp
            })
            current = current.next
        return result

    @classmethod
    def from_list(cls, data_list):
        """Create linked list from list of dictionaries"""
        ll = cls()
        for item in reversed(data_list):  # Reverse to maintain order
            ll.insert(item["score"], item["timestamp"])
        return ll

# ============= Tetris Piece Definitions =============
# Each piece is defined by its shape matrix and color
SHAPES = [
    {"shape": [[1, 1, 1], [0, 1, 0]], "color": "purple"},   # T piece
    {"shape": [[1, 1, 1, 1]], "color": "cyan"},             # I piece
    {"shape": [[1, 1], [1, 1]], "color": "yellow"},         # O piece
    {"shape": [[0, 1, 1], [1, 1, 0]], "color": "green"},    # S piece
    {"shape": [[1, 1, 0], [0, 1, 1]], "color": "red"},      # Z piece
    {"shape": [[1, 0], [1, 0],[1, 1]], "color": "orange"},  # L piece
]

class TetrisClient:
    """
    Main Tetris game client class.
    Handles game window, UI, game logic, networking, and sound.
    """
    
    def __init__(self):
        """Initialize the game client and set up the main window"""
        # ============= Window Setup =============
        self.root = tk.Tk()
        self.root.title("Tetris Battle")
        
        # Center window on screen
        window_width = 1000
        window_height = 700
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # ============= Game State Initialization =============
        self.next_queue = [self.new_piece() for _ in range(3)]  # Queue for next pieces
        self.username = None
        self.opponent_name = "OPPONENT"
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((HOST, PORT))
        self.running = False
        self.paused = False
        self.hold_piece = None
        self.hold_used = False
        
        # Add state tracking for board updates
        self.prev_board_state = [[0]*COLUMNS for _ in range(ROWS)]
        self.prev_piece_state = {}
        self.last_board_update = 0
        self.board_update_interval = 0.1  # 100ms minimum between updates
        
        # ============= Scoring System Initialization =============
        self.score = 0
        self.level = 1
        self.total_lines_cleared = 0
        self.combo = 0
        self.last_clear_was_tetris = False
        self.soft_drop_points = 0
        self.hard_drop_points = 0
        self.score_history = LinkedList()
        
        # Load existing scores and leaderboard
        self.load_local_data()
        
        # ============= Audio System Setup =============
        self.setup_audio()
        
        # ============= Start Game =============
        self.show_initial_background()
        self.root.after(3000, self.lobby_ui)
        threading.Thread(target=self.listen_server, daemon=True).start()
        self.root.mainloop()

    def load_local_data(self):
        """Load scores and leaderboard from local files"""
        # Load player scores
        if os.path.exists(SCORES_FILE):
            try:
                with open(SCORES_FILE, 'r') as f:
                    data = json.load(f)
                    self.score_history = LinkedList.from_list(data)
            except:
                self.score_history = LinkedList()

        # Load leaderboard
        if os.path.exists(LEADERBOARD_FILE):
            try:
                with open(LEADERBOARD_FILE, 'r') as f:
                    self.leaderboard_data = json.load(f)
            except:
                self.leaderboard_data = {}
        else:
            self.leaderboard_data = {}

    def save_local_data(self):
        """Save scores and leaderboard to local files"""
        # Save player scores
        with open(SCORES_FILE, 'w') as f:
            json.dump(self.score_history.to_list(), f)

        # Save leaderboard
        with open(LEADERBOARD_FILE, 'w') as f:
            json.dump(self.leaderboard_data, f)

    def setup_audio(self):
        """Initialize and configure the audio system"""
        pygame.mixer.init()
        pygame.mixer.set_num_channels(16)
        
        # Set up audio channels
        self.clear_line_channel = pygame.mixer.Channel(1)
        self.drop_sound_channel = pygame.mixer.Channel(2)
        
        # Load and configure background music
        pygame.mixer.music.load("bgm.mp3")
        pygame.mixer.music.set_volume(0.70)
        pygame.mixer.music.play(loops=-1, start=0.0)
        
        # Load sound effects
        self.drop_sound = pygame.mixer.Sound("drps.mp3")
        self.clear_sound = pygame.mixer.Sound("lcs.wav")
        self.gameover_music = pygame.mixer.Sound("gos.mp3")
        
        # Set sound effect volumes
        self.drop_sound.set_volume(0.1)
        self.clear_sound.set_volume(0.5)

    def show_initial_background(self):
        """Display the initial background image"""
        screen_width = 1000
        screen_height = 700
        
        # Load and resize background image
        bg_image = Image.open("bgm.png")
        bg_image = bg_image.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(bg_image)
        
        # Create and display canvas
        self.canvas = tk.Canvas(self.root, width=screen_width, height=screen_height)
        self.canvas.place(x=0, y=0)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.bg_photo)

    def lobby_ui(self):
        self.clear_window()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        bg_image = Image.open("bgm.png")
        bg_image = bg_image.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
        bg_photo = ImageTk.PhotoImage(bg_image)
        
        self.root.bind("<Escape>", lambda event: self.root.destroy())
        self.background_label = tk.Label(self.root, image=bg_photo)
        self.background_label.image = bg_photo
        self.background_label.place(relwidth=1, relheight=1)

    # Show only Start button initially
        self.start_frame = tk.Frame(self.root, bg='#04143f', bd=10, padx=10, pady=10)
        self.start_frame.place(relx=0.5, rely=0.57, anchor='center', width=200, height=80)

        self.start_button = tk.Button(self.start_frame, text="START", font=('Helvetica', 20, 'bold'),
                                  bg='#fb18bf', fg='white', relief='raised', bd=5,
                                  command=self.show_join_lobby_ui)
        self.start_button.pack(expand=True, fill='both')
    
    def show_join_lobby_ui(self):
    # Remove start button/frame
        self.start_frame.destroy()

    # Create lobby frame with name entry and Join Lobby button
        self.lobby_frame = tk.Frame(self.root, bg='#04143f', bd=10, padx=10, pady=10)
        self.lobby_frame.place(relx=0.5, rely=0.5, anchor='center', width=320, height=220)

        tk.Label(self.lobby_frame, text="Enter your name:", font=('Helvetica', 20, 'bold'), fg='white', bg='#04143f').place(x=20, y=10)

        self.name_entry = tk.Entry(self.lobby_frame, font=('Lucida Sans Typewriter', 15), bd=3, relief='solid', width=20)
        self.name_entry.place(x=15, y=60)
        self.name_entry.bind("<Return>", lambda event: self.join_lobby())

        tk.Button(self.lobby_frame, text="Join Lobby", font=('Helvetica', 15, 'bold'), command=self.join_lobby,
              bg='#fb18bf', fg='white', relief='raised', bd=5, width=15).place(x=50, y=110)
    
    def join_lobby(self):
        self.username = self.name_entry.get()
        if self.username:
            self.conn.send(self.username.encode())
            self.lobby_screen()
            self.conn.send(json.dumps({"type": "request_lobby"}).encode() + b'\n')
            
    def lobby_screen(self):
        self.clear_window()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Load and resize background
        bg_image = Image.open("lobby_bg.png")
        bg_image = bg_image.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
        bg_photo = ImageTk.PhotoImage(bg_image)

        # Create a background label and place it behind other UI elements
        self.background_label = tk.Label(self.root, image=bg_photo)
        self.background_label.image = bg_photo  # Keep a reference to avoid garbage collection
        self.background_label.place(relwidth=1, relheight=1)

        # Main lobby box frame
        self.lobby_box = tk.Frame(self.root, bg='#04143f', bd=10, padx=20, pady=20)
        self.lobby_box.place(relx=0.5, rely=0.5, anchor='center')
        

        # Status label
        self.status_label = tk.Label(self.lobby_box, text="Waiting for opponent...", font=('Helvetica', 16), fg='pink', bg='#04143f')
        self.status_label.pack(pady=(0, 10))

        # Players frame
        self.players_frame = tk.Frame(self.lobby_box, bg='#04143f')
        self.players_frame.pack(pady=(0, 10))

        # Ready button
        self.ready = False
        self.ready_button = tk.Button(self.lobby_box, text="Ready", font=('Helvetica', 14, 'bold'), 
                                    command=self.toggle_ready, bg='#fb18bf', fg='white', 
                                    relief='raised', bd=5, width=15)
        self.ready_button.pack(pady=(10, 0))

        # Add Leaderboard button
        leaderboard_btn = tk.Button(self.lobby_box, text="📊 Leaderboard", 
                                  command=self.show_lobby_leaderboard,
                                  font=('Helvetica', 14, 'bold'),
                                  bg='#ffd369', fg='#222831',
                                  relief='raised', bd=5, width=15)
        leaderboard_btn.pack(pady=(10, 0))

    def toggle_ready(self):
        self.ready = not self.ready
        msg = {"type": "ready", "ready": self.ready}
        self.conn.send(json.dumps(msg).encode())
        self.ready_button.config(text="Unready" if self.ready else "Ready")
        
    def listen_server(self):
        buffer = ""
        last_update_time = 0
        update_interval = 1/60  # 60 FPS
        
        while True:
            try:
                data = self.conn.recv(4096)
                if not data:
                    break
                buffer += data.decode()

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    msg = json.loads(line)

                    if msg['type'] == 'lobby' and hasattr(self, 'players_frame') and self.players_frame.winfo_exists():
                        self.update_lobby(msg['players'])
                        # Set opponent name from the player list
                        for p in msg['players']:
                            if p['name'] != self.username:
                                self.opponent_name = p['name']

                    elif msg['type'] == 'start':
                        self.show_countdown_and_start()

                    elif msg['type'] == 'score':
                        if hasattr(self, 'opponent_score_box') and self.opponent_score_box.winfo_exists():
                            self.opponent_score_box.config(text=str(msg['value']))
                        players_scores = [(self.username, self.score), (self.opponent_name, msg['value'])]
                        self.update_leaderboard(players_scores)

                    elif msg['type'] == 'board':
                        current_time = time.time()
                        if current_time - last_update_time >= update_interval:
                            if hasattr(self, 'opponent_canvas') and self.opponent_canvas.winfo_exists():
                                self.draw_board(
                                    self.opponent_canvas,
                                    msg['board'],
                                    msg.get('current_piece')
                                )
                            last_update_time = current_time

                    elif msg['type'] == 'chat':
                        self.display_chat_message(msg['from'], msg['message'])
                    
                    elif msg['type'] == 'system':
                        if hasattr(self, 'system_label') and self.system_label.winfo_exists():
                            self.system_label.config(text=msg['message'])

                    elif msg['type'] == 'game_over':
                        self.running = False
                        if msg.get("result") == "win":
                            self.show_end_screen(f"🎉 You Win!")
                        elif msg.get("result") == "lose":
                            self.show_end_screen(f"💀 You Lose!")

                    elif msg['type'] == 'rematch_request':
                        if hasattr(self, 'rematch_status'):
                            self.rematch_status.config(text=f"{msg['from']} wants a rematch!")
                            # Create accept/decline buttons
                            btn_frame = tk.Frame(self.root, bg="#04143f")
                            btn_frame.place(relx=0.15, rely=0.70, anchor='w')  # Align with other widgets
                            
                            # Style for accept button
                            accept_style = {
                                "font": ("Helvetica", 14, "bold"),
                                "bg": "#04143f",  # Match container background
                                "fg": "#ffd369",  # Match text color
                                "activebackground": "#1a1f5a",  # Slightly lighter for hover effect
                                "activeforeground": "#ffd369",
                                "bd": 0,
                                "relief": "flat",
                                "width": 12,
                                "height": 2,
                                "cursor": "hand2"
                            }

                            # Style for decline button
                            decline_style = {
                                "font": ("Helvetica", 14, "bold"),
                                "bg": "#04143f",  # Match container background
                                "fg": "#ffd369",  # Match text color
                                "activebackground": "#1a1f5a",  # Slightly lighter for hover effect
                                "activeforeground": "#ffd369",
                                "bd": 0,
                                "relief": "flat",
                                "width": 12,
                                "height": 2,
                                "cursor": "hand2"
                            }

                            accept_btn = tk.Button(btn_frame, text="✓ Accept", command=self.accept_rematch, **accept_style)
                            accept_btn.pack(side='left', padx=15)
                            
                            decline_btn = tk.Button(btn_frame, text="✕ Decline", command=self.decline_rematch, **decline_style)
                            decline_btn.pack(side='left', padx=15)

                    elif msg['type'] == 'rematch_accepted':
                        # Reset game state and return to lobby
                        self.score = 0
                        self.level = 1
                        self.total_lines_cleared = 0
                        self.combo = 0
                        self.last_clear_was_tetris = False
                        self.soft_drop_points = 0
                        self.hard_drop_points = 0
                        self.board = [[0]*COLUMNS for _ in range(ROWS)]
                        self.next_queue = [self.new_piece() for _ in range(3)]
                        self.current_piece = self.next_queue.pop(0)
                        self.current_piece['x'] = COLUMNS // 2 - 1
                        self.current_piece['y'] = 0
                        self.hold_piece = None
                        self.hold_used = False
                        self.lobby_screen()
                        self.conn.send(json.dumps({"type": "request_lobby"}).encode() + b'\n')

            except Exception as e:
                print("Error in client listener:", e)
                break

    def show_countdown_and_start(self):
        self.clear_window()
        self.root.update()

        bg_image = Image.open("start_bg.png")
        bg_image = bg_image.resize((self.root.winfo_screenwidth(), self.root.winfo_screenheight()), Image.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(bg_image)  # Save reference to avoid garbage collection

        bg_label = tk.Label(self.root, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Make countdown_label an instance variable so we can check if it exists
        self.countdown_label = tk.Label(self.root, text="The game will start in 3...", 
                                      font=("Helvetica", 36, "bold"),
                                      fg="pink", bg="#000000", bd=10, relief="ridge")
        self.countdown_label.place(relx=0.5, rely=0.5, anchor='center')

        def update_countdown(count):
            # Check if the label still exists before updating
            if hasattr(self, 'countdown_label') and self.countdown_label.winfo_exists():
                if count > 0:
                    self.countdown_label.config(text=f"The game will start in {count}...")
                    self.root.after(1000, update_countdown, count - 1)
                else:
                    self.start_game()

        self.root.after(1000, update_countdown, 2)  # Already showed 3, continue with 2, 1...


    def update_lobby(self, players):
        # Clear existing players display
        for widget in self.players_frame.winfo_children():
            widget.destroy()
        
        # Display each player's status
        for player in players:
            text = f"{player['name']} - {'Ready' if player['ready'] else 'Not Ready'}"
            label = tk.Label(self.players_frame, text=text, font=('Arial', 18), 
                           fg='white', bg='#34495E', anchor='center', 
                           width=30, justify='center')
            label.pack(pady=5, padx=10)

        # Update status label based on number of players
        if len(players) < 2:
            self.status_label.config(text="Waiting for opponent...")
        elif all(player['ready'] for player in players):
            self.status_label.config(text="Both players ready! Game starting soon...")
        else:
            self.status_label.config(text="Waiting for opponent to be ready...")

    def start_game(self):
        self.clear_window()
        pygame.mixer.music.stop()

        # --- Set up background ---
        bg_image = Image.open("m_bg.png")
        bg_image = bg_image.resize((self.root.winfo_screenwidth(), self.root.winfo_screenheight()), Image.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(bg_image)
        bg_label = tk.Label(self.root, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        pygame.mixer.music.load("sbgm.mp3")  # Change to your actual game music file
        pygame.mixer.music.set_volume(0.3)
        pygame.mixer.music.play(loops=-1, start=0.0)

        # --- Main game area ---
        main_frame = tk.Frame(self.root, bg="#393e46", bd=4, relief="ridge")
        main_frame.pack(pady=30)


  # Player board with score above
        player_frame = tk.Frame(main_frame, bg="#222831", bd=2, relief="groove")
        player_frame.grid(row=0, column=0, padx=20, pady=10)

  # Score row above the board
        score_row = tk.Frame(player_frame, bg="#222831")
        score_row.pack(pady=(0, 2))

        tk.Label(score_row, text="SCORE", fg="#ffd369", bg="#222831", font=("Arial", 10, "bold")).pack(side="left", padx=(0, 4))
        self.score_box = tk.Label(score_row, text="0", fg="#ffd369", bg="#393e46", font=("Arial", 11, "bold"), width=6, relief="sunken")
        self.score_box.pack(side="left")

  # Username label
        tk.Label(player_frame, text=self.username, fg="#ffd369", bg="#222831", font=("Arial", 14, "bold")).pack(pady=5)

  # Game board canvas (unchanged size)
        self.canvas = tk.Canvas(player_frame, width=COLUMNS*TILE_SIZE, height=ROWS*TILE_SIZE, bg='black', highlightthickness=2, highlightbackground="#ffd369")
        self.canvas.pack()

        # Next/Hold panel
        side_panel = tk.Frame(main_frame, bg="#393e46")
        side_panel.grid(row=0, column=1, padx=10)
        tk.Label(side_panel, text="NEXT", bg="#393e46", fg="#ffd369", font=("Arial", 12, "bold")).pack(pady=(0,5))
        self.next_canvas1 = tk.Canvas(side_panel, width=90, height=90, bg="black", highlightthickness=1, highlightbackground="#ffd369")
        self.next_canvas1.pack()
        self.next_canvas2 = tk.Canvas(side_panel, width=90, height=90, bg="black", highlightthickness=1, highlightbackground="#ffd369")
        self.next_canvas2.pack(pady=(5,0))
        self.next_canvas3 = tk.Canvas(side_panel, width=90, height=90, bg="black", highlightthickness=1, highlightbackground="#ffd369")
        self.next_canvas3.pack(pady=(5,0))
        tk.Label(side_panel, text="HOLD", bg="#393e46", fg="#ffd369", font=("Arial", 12, "bold")).pack(pady=(15,5))
        self.hold_canvas = tk.Canvas(side_panel, width=90, height=90, bg="black", highlightthickness=1, highlightbackground="#ffd369")
        self.hold_canvas.pack()

        # Opponent board
        # Opponent board with score above
        opponent_frame = tk.Frame(main_frame, bg="#222831", bd=2, relief="groove")
        opponent_frame.grid(row=0, column=2, padx=20, pady=10)

        # Opponent score row
        opponent_score_row = tk.Frame(opponent_frame, bg="#222831")
        opponent_score_row.pack(pady=(0, 2))
        tk.Label(opponent_score_row, text="SCORE", fg="#ffd369", bg="#222831", font=("Arial", 10, "bold")).pack(side="left", padx=(0, 4))
        self.opponent_score_box = tk.Label(opponent_score_row, text="0", fg="#ffd369", bg="#393e46", font=("Arial", 11, "bold"), width=6, relief="sunken")
        self.opponent_score_box.pack(side="left")

        # Opponent name label
        tk.Label(opponent_frame, text=self.opponent_name, fg="#ffd369", bg="#222831", font=("Arial", 14, "bold")).pack(pady=5)

        # Opponent board canvas (unchanged size)
        self.opponent_canvas = tk.Canvas(opponent_frame, width=COLUMNS*TILE_SIZE, height=ROWS*TILE_SIZE, bg='black', highlightthickness=2, highlightbackground="#ffd369")
        self.opponent_canvas.pack()

# Add this after the opponent_canvas.pack() line in start_game method
# Chat box frame
        chat_frame = tk.Frame(main_frame, bg="#222831", bd=2, relief="groove")
        chat_frame.grid(row=0, column=3, padx=10, pady=10, sticky="ns")

# Add "Chatbox" label
        tk.Label(chat_frame, text="Chatbox", fg="#ffd369", bg="#222831",
         font=("Arial", 12, "bold")).pack(pady=(5, 0))

# Chat log (text display area)
        self.chat_log = tk.Text(chat_frame, width=30, height=25, state='disabled', 
                        bg="#393e46", fg="#ffd369", font=("Arial", 12))
        self.chat_log.pack(padx=5, pady=5)


        # Chat input frame
        chat_input_frame = tk.Frame(chat_frame, bg="#222831")
        chat_input_frame.pack(fill='x', padx=5, pady=(0,5))

        # Chat entry
        self.chat_entry = tk.Entry(chat_input_frame, width=30,font=("Arial", 10),
                                 bg="#393e46", fg="#ffd369", insertbackground="#ffd369")
        self.chat_entry.pack(side='left', padx=(0,5))
        self.chat_entry.bind("<Return>", self.send_chat_message)

        # Send button
        send_button = tk.Button(chat_input_frame, text="Send", command=self.send_chat_message,
                              bg="#ffd369", fg="#222831", font=("Helvetica", 10, "bold"),
                              relief="raised", bd=2)
        send_button.pack(side='right')

        # Create a frame below the chat box for system messages
        system_help_frame = tk.Frame(chat_frame, bg="#222831")
        system_help_frame.pack(pady=(5, 5), fill='x')

        self.system_label = tk.Label(
            system_help_frame,
            text="SYSTEM: ",
            fg="red",
            bg="#222831",
            font=("Arial", 10, "bold"),
            anchor="w"
        )
        self.system_label.pack(side='left', padx=(5, 10))
        # --- Instructions bar at the bottom ---
      # Create a frame to hold the "?" icon (near send button, or wherever appropriate)
        tooltip_frame = tk.Frame(chat_frame, bg="#222831")
        tooltip_frame.pack(pady=(0, 5))  # Adjust as needed for positioning

# Create the "?" icon
        help_icon = tk.Label(chat_frame, text="❓", bg="#ffd369", fg="#222831",
                     font=("Arial", 14, "bold"), cursor="question_arrow")
        help_icon.place(x=245, y=530)

        help_icon.bind("<Enter>", self.show_tooltip)
        help_icon.bind("<Leave>", self.hide_tooltip)
        
# Create the tooltip label (hidden by default)
        tooltip_text = (
            "Controls:\n"
            "← = Move Left   "
            "\n→ = Move Right   "
            "\n↓ = Soft Drop   "
            "\n↑ = Rotate"
            "\nSpace: Hard Drop " 
            "\nShift: Hold Piece"
        )
        self.tooltip_label = tk.Label(self.root, text=tooltip_text, bg="#393e46", fg="#ffd369",
                         font=("Helvetica", 12), relief="solid", borderwidth=1, justify='left')
        self.tooltip_label.place_forget()  # Hide initially

        # --- Game logic setup ---
        self.board = [[0]*COLUMNS for _ in range(ROWS)]
        self.current_piece = self.next_queue.pop(0)
        self.current_piece['x'] = COLUMNS // 2 - 1
        self.current_piece['y'] = 0
        self.next_queue.append(self.new_piece())
        self.hold_piece = None
        self.hold_used = False
        self.score = 0
        self.running = True

        self.root.bind("<Key>", self.key_press)

        # Add leaderboard setup here
        self.setup_leaderboard()
        self.update_leaderboard([
            (self.username or "You", self.score),
            (self.opponent_name, 0)
        ])
        self.game_loop()
    
    def setup_leaderboard(self):
        # Create a leaderboard frame at top-right corner
        self.leaderboard_frame = tk.Frame(self.root, bg="#222244", bd=2, relief="sunken")
        self.leaderboard_frame.place(relx=0.98, rely=0.05, anchor='ne', width=150, height=150)

        title = tk.Label(self.leaderboard_frame, text="Leaderboard", fg="#ffd369", bg="#222244", font=("Helvetica", 14, "bold"))
        title.pack(pady=5)

        self.leaderboard_list = tk.Listbox(self.leaderboard_frame, bg="#333355", fg="#ffd369", font=("Helvetica", 13))
        self.leaderboard_list.pack(fill="both", expand=True, padx=5, pady=5)

        # Add search button beside leaderboard
        self.search_button = tk.Button(self.root, text="🔍 Search Player",
                                   command=self.open_player_search_popup,
                                   font=("Helvetica", 10, "bold"), bg="#fb18bf", fg="white",
                                   relief="raised", bd=3)
        # Position it beside leaderboard
        self.search_button.place(relx=0.98, rely=0.25, anchor='ne')  # Position relative to right edge

    def open_player_search_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Search Player")
        popup.geometry("400x500")  # Made window larger to accommodate score history
        popup.configure(bg="#222831")

        # Search section
        search_frame = tk.Frame(popup, bg="#222831")
        search_frame.pack(pady=10)

        tk.Label(search_frame, text="Enter player name:", font=("Helvetica", 12, "bold"),
                 bg="#222831", fg="#ffd369").pack(pady=5)

        entry = tk.Entry(search_frame, font=("Helvetica", 12), bg="#393e46", fg="#ffd369", insertbackground="#ffd369")
        entry.pack(pady=5)

        # Result section
        result_frame = tk.Frame(popup, bg="#222831")
        result_frame.pack(pady=10)

        result_label = tk.Label(result_frame, text="", font=("Helvetica", 11), bg="#222831", fg="white")
        result_label.pack(pady=5)

        # Score history section
        history_frame = tk.Frame(popup, bg="#222831")
        history_frame.pack(pady=10, fill="both", expand=True)

        tk.Label(history_frame, text="Game History:", font=("Helvetica", 12, "bold"),
                bg="#222831", fg="#ffd369").pack(pady=5)

        # Create a frame for the score list with scrollbar
        list_frame = tk.Frame(history_frame, bg="#222831")
        list_frame.pack(fill="both", expand=True, padx=10)

        # Scrollbar
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        # Score history list
        score_list = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                              bg="#393e46", fg="#ffd369",
                              font=("Helvetica", 11),
                              selectmode="single",
                              height=10)
        score_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=score_list.yview)

        def search():
            name_to_find = entry.get().strip()
            # Get current players from leaderboard
            players_scores = []
            for i in range(self.leaderboard_list.size()):
                text = self.leaderboard_list.get(i)
                name, score = text.split(": ")
                players_scores.append((name, int(score)))

            sorted_players = sorted(players_scores, key=lambda x: x[0].lower())
            index = self.binary_search_player(sorted_players, name_to_find)

            if index != -1:
                found_name, found_score = sorted_players[index]
                result_label.config(text=f"✅ {found_name} found!\nCurrent Score: {found_score}", fg="#7CFC00")
                
                # Clear previous score history
                score_list.delete(0, tk.END)
                
                # Get and display score history for the found player
                current = self.score_history.head
                while current:
                    score_list.insert(0, f"Score: {current.value} - {current.timestamp}")  # Insert at beginning to show newest first
                    current = current.next
            else:
                result_label.config(text=f"❌ '{name_to_find}' not found.", fg="red")
                score_list.delete(0, tk.END)  # Clear score history if player not found

        search_btn = tk.Button(search_frame, text="Search", command=search,
                               font=("Helvetica", 11, "bold"), bg="#ffd369", fg="#222831", relief="raised", bd=2)
        search_btn.pack(pady=5)

        # Close button
        close_btn = tk.Button(popup, text="Close", command=popup.destroy,
                            font=("Helvetica", 11, "bold"),
                            bg="#fb18bf", fg="white",
                            relief="raised", bd=3)
        close_btn.pack(pady=10)

        # Make popup modal
        popup.transient(self.root)
        popup.grab_set()
        self.root.wait_window(popup)

    def update_leaderboard(self, players_scores):
        """Update leaderboard with new scores"""
        # Update local leaderboard
        for name, score in players_scores:
            if name not in self.leaderboard_data:
                self.leaderboard_data[name] = []
            self.leaderboard_data[name].append({
                "score": score,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # Save to file
        self.save_local_data()
        
        # Update display
        self.leaderboard_list.delete(0, tk.END)
        sorted_scores = sorted(players_scores, key=lambda x: x[1], reverse=True)
        for username, score in sorted_scores:
            self.leaderboard_list.insert(tk.END, f"{username}: {score}")

    def show_tooltip(self, event):
        x = event.widget.winfo_rootx()
        y = event.widget.winfo_rooty() + 20
        self.tooltip_label.place(x=x, y=y)

    def hide_tooltip(self, event):
        self.tooltip_label.place_forget()
# Bind hover events to the icon

    def send_chat_message(self, event=None):
        message = self.chat_entry.get().strip()
        if message:
            try:
            # Send message to server
                self.conn.send(json.dumps({
                'type': 'chat',
                'from': self.username, 
                'message': message
            }).encode())
            # Clear the entry
                self.chat_entry.delete(0, tk.END)
            except Exception as e:
                print("Failed to send chat:", e)

    def display_chat_message(self, sender, message):
        try:
            self.chat_log.config(state='normal')
    # Add timestamp
            timestamp = time.strftime("%H:%M")
    # Format the message with sender name and timestamp
            formatted_message = f"[{timestamp}] {sender}: {message}\n"
            self.chat_log.insert(tk.END, formatted_message)
    # Auto-scroll to bottom
            self.chat_log.see(tk.END)
            self.chat_log.config(state='disabled')
        except Exception as e:
            print(f"Error displaying chat message: {e}")
# QUEUE
    def new_piece(self):
        piece = random.choice(SHAPES)
        return {"shape": piece["shape"], "color": piece["color"], "x": COLUMNS // 2 - 1, "y": 0}
    
    def draw_tile(self, canvas, x, y, color):
        """Draw a single tile"""
        # Main block
        canvas.create_rectangle(
            x * TILE_SIZE, y * TILE_SIZE,
            (x + 1) * TILE_SIZE, (y + 1) * TILE_SIZE,
            fill=color, outline="#444444", width=1
        )
        # Shine stripe (top left)
        canvas.create_rectangle(
            x * TILE_SIZE + 2, y * TILE_SIZE + 2,
            x * TILE_SIZE + TILE_SIZE // 2, y * TILE_SIZE + 6,
            fill="white", outline="", stipple="gray25"
        )
        # Shadow stripe (bottom right)
        canvas.create_rectangle(
            x * TILE_SIZE + TILE_SIZE // 2, y * TILE_SIZE + TILE_SIZE - 6,
            (x + 1) * TILE_SIZE - 2, (y + 1) * TILE_SIZE - 2,
            fill="#222831", outline="", stipple="gray25"
        )
        # Subtle border
        canvas.create_rectangle(
            x * TILE_SIZE, y * TILE_SIZE,
            (x + 1) * TILE_SIZE, (y + 1) * TILE_SIZE,
            outline="#888888", width=1
        )

    def draw_board(self, canvas, board, piece=None):
        """Draw the game board with optimized rendering"""
        if not canvas.winfo_exists():
            return
            
        # Store the current state to prevent unnecessary redraws
        if not hasattr(self, '_last_board_state'):
            self._last_board_state = {}
            
        # Create a unique key for this canvas
        canvas_id = str(canvas)
        
        # Check if the board state has changed
        current_state = (str(board), str(piece) if piece else None)
        if canvas_id in self._last_board_state and self._last_board_state[canvas_id] == current_state:
            return
            
        # Update the stored state
        self._last_board_state[canvas_id] = current_state
        
        # Clear the canvas
        canvas.delete("all")
        
        # Draw grid
        for i in range(COLUMNS + 1):
            canvas.create_line(
                i * TILE_SIZE, 0,
                i * TILE_SIZE, ROWS * TILE_SIZE,
                fill="#444444",
                width=1
            )
        for i in range(ROWS + 1):
            canvas.create_line(
                0, i * TILE_SIZE,
                COLUMNS * TILE_SIZE, i * TILE_SIZE,
                fill="#444444",
                width=1
            )
        
        # Draw the board pieces
        for y in range(ROWS):
            for x in range(COLUMNS):
                if board[y][x]:
                    self.draw_tile(canvas, x, y, board[y][x])
        
        # Draw current piece if provided
        if piece:
            for y, row in enumerate(piece['shape']):
                for x, val in enumerate(row):
                    if val:
                        self.draw_tile(canvas, piece['x'] + x, piece['y'] + y, piece['color'])
        
        # Update the canvas
        canvas.update_idletasks()

    def draw_next(self):
            self.next_canvas1.delete("all")
            self.next_canvas2.delete("all")
            self.next_canvas3.delete("all")
            next_canvases = [self.next_canvas1, self.next_canvas2, self.next_canvas3]
            for idx, piece in enumerate(self.next_queue):
                    canvas = next_canvases[idx]
                    for y, row in enumerate(piece['shape']):
                            for x, val in enumerate(row):
                                    if val:
                                            canvas.create_rectangle(x*20, y*20, (x+1)*20, (y+1)*20, fill=piece["color"], outline="white")
    def draw_hold(self):
        self.hold_canvas.delete("all")
        if not self.hold_piece:
            return
        for y, row in enumerate(self.hold_piece['shape']):
            for x, val in enumerate(row):
                if val:
                    self.hold_canvas.create_rectangle(x*20, y*20, (x+1)*20, (y+1)*20, fill=self.hold_piece["color"], outline="white")

    def draw(self):
        self.canvas.delete("all")
        for y in range(ROWS):
            for x in range(COLUMNS):
                if self.board[y][x]:
                    self.draw_tile(self.canvas, x, y, self.board[y][x])
        for y, row in enumerate(self.current_piece['shape']):
            for x, val in enumerate(row):
                if val:
                    self.draw_tile(self.canvas, self.current_piece['x'] + x, self.current_piece['y'] + y, self.current_piece["color"])
        for i in range(COLUMNS + 1):
            self.canvas.create_line(i * TILE_SIZE, 0, i * TILE_SIZE, ROWS * TILE_SIZE, fill="gray")
        for i in range(ROWS + 1):
            self.canvas.create_line(0, i * TILE_SIZE, COLUMNS * TILE_SIZE, i * TILE_SIZE, fill="gray")
        self.draw_next()
        self.draw_hold()

    def move(self, dx, dy):
        if dy == 1:  # Soft drop
            self.soft_drop_points += 1
            self.drop_sound.play()
        self.current_piece['x'] += dx
        self.current_piece['y'] += dy
        if self.collision():
            self.current_piece['x'] -= dx
            self.current_piece['y'] -= dy
            if dy == 1:
                self.soft_drop_points -= 1  # Undo if move failed
            return False
        return True
    
    def rotate(self):
        shape = self.current_piece['shape']
        rotated = list(zip(*shape[::-1]))
        self.current_piece['shape'] = rotated
        if self.collision():
            self.current_piece['shape'] = shape

    def collision(self):
        shape = self.current_piece['shape']
        for y, row in enumerate(shape):
            for x, val in enumerate(row):
                if val:
                    px = self.current_piece['x'] + x
                    py = self.current_piece['y'] + y
                    if px < 0 or px >= COLUMNS or py >= ROWS or (py >= 0 and self.board[py][px]):
                        return True
        return False

    def freeze(self):
        shape = self.current_piece['shape']
        for y, row in enumerate(shape):
            for x, val in enumerate(row):
                if val:
                    px = self.current_piece['x'] + x
                    py = self.current_piece['y'] + y
                    if 0 <= py < ROWS:
                        self.board[py][px] = self.current_piece["color"]
        self.clear_lines()
        self.current_piece = self.next_queue.pop(0)
        self.current_piece['x'] = COLUMNS // 2 - 1
        self.current_piece['y'] = 0
        self.next_queue.append(self.new_piece())
        self.hold_used = False
        if self.collision():
            self.running = False
            try:
                # Send lose message to server
                self.conn.send(json.dumps({"type": "lose"}).encode() + b'\n')
                # Show game over screen immediately
                self.show_end_screen("💀 You Lose!")
            except Exception as e:
                print(f"Failed to send lose message: {e}")
                # Still show game over screen even if message fails
                self.show_end_screen("💀 You Lose!")

    def clear_lines(self):
        """
        Handle line clearing and scoring system
        - Removes completed lines
        - Updates score based on lines cleared
        - Applies combo and Tetris bonuses
        - Updates level based on total lines cleared
        """
        score_gained = 0 
        lines_cleared = 0
        new_board = []
        
        # Check for and remove completed lines
        for row in self.board:
            if all(row):
                lines_cleared += 1
            else:
                new_board.append(row)
        
        # Add new empty lines at top
        for _ in range(lines_cleared):
            new_board.insert(0, [0]*COLUMNS)
        self.board = new_board
        
        # Update total lines and level
        self.total_lines_cleared += lines_cleared
        self.level = self.total_lines_cleared // 10 + 1
        
        # Calculate score multiplier based on level
        multiplier = 1 + (self.level - 1) * 0.1
        
        # Base scores for different line clears
        base_scores = {1: 100, 2: 300, 3: 500, 4: 800}
        
        # Handle line clear sound and scoring
        if lines_cleared > 0:
            # Play clear sound
            if not self.clear_line_channel.get_busy():
                self.clear_line_channel.play(self.clear_sound)
            else:
                self.clear_line_channel.stop()
                self.clear_line_channel.play(self.clear_sound)
            
            # Calculate score with bonuses
            if lines_cleared == 4:  # Tetris
                if self.last_clear_was_tetris:
                    score_gained += 400 * multiplier  # Back-to-back Tetris bonus
                self.last_clear_was_tetris = True
            else:
                self.last_clear_was_tetris = False
            
            # Add combo bonus
            if self.combo > 0:
                score_gained += 50 * self.combo * multiplier
            self.combo += 1
            
            self.score += int(score_gained)
        else:
            self.combo = 0
            self.last_clear_was_tetris = False
        
        # Add drop points
        self.score += int(self.soft_drop_points * multiplier)
        self.score += int(self.hard_drop_points * multiplier)
        self.soft_drop_points = 0
        self.hard_drop_points = 0
        
        # Track score in history
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.score_history.insert(self.score, current_time)
        
        # Update display and send score to server
        self.score_box.config(text=str(self.score))
        self.conn.send(json.dumps({
            "type": "score",
            "value": self.score,
            "level": self.level
        }).encode())

    def game_loop(self):
        """Main game loop"""
        if not self.running or self.paused:
            return
        
        current_time = time.time()
        
        # Move piece down and handle collision
        if not self.move(0, 1):
            self.freeze()
        
        # Only send board update if enough time has passed and state has changed
        if (current_time - self.last_board_update >= self.board_update_interval and 
            (self.prev_board_state != self.board or 
             self.prev_piece_state != self.current_piece)):
            
            try:
                self.conn.send(json.dumps({
                    "type": "board",
                    "board": self.board,
                    "current_piece": {
                        "shape": self.current_piece['shape'],
                        "color": self.current_piece['color'],
                        "x": self.current_piece['x'],
                        "y": self.current_piece['y']
                    }
                }).encode() + b'\n')
                
                # Update state tracking
                self.prev_board_state = [row[:] for row in self.board]  # Deep copy
                self.prev_piece_state = self.current_piece.copy()
                self.last_board_update = current_time
                
            except BrokenPipeError:
                print("Disconnected while sending board update")
                self.running = False
            except Exception as e:
                print(f"Error sending board update: {e}")
        
        # Update display
        self.draw()
        
        # Schedule next frame with speed based on level
        speed = max(50, 500 - (self.level - 1) * 50)  # Decrease delay as level increases
        self.root.after(speed, self.game_loop)

# STACK LIFO
    def hold_current_piece(self):
        if self.hold_used:
            return
        self.hold_used = True
        if not self.hold_piece:
            self.hold_piece = self.current_piece
            self.current_piece = self.new_piece()
            self.next_piece = self.new_piece()
        else:
            self.hold_piece, self.current_piece = self.current_piece, self.hold_piece
        self.current_piece['x'] = COLUMNS // 2 - 1
        self.current_piece['y'] = 0
        self.draw_hold()

    def hard_drop(self):
        drop_distance = 0
        while self.move(0, 1):
            drop_distance += 1
        self.hard_drop_points += drop_distance * 2
        if not self.drop_sound_channel.get_busy():
            self.drop_sound_channel.play(self.drop_sound)
        else:
            self.drop_sound_channel.stop()
            self.freeze()

    def key_press(self, event):
        if not self.running or self.paused:
            return
        if event.keysym == 'Left':
            self.move(-1, 0)
        elif event.keysym == 'Right':
            self.move(1, 0)
        elif event.keysym == 'Down':
            self.move(0, 1)
        elif event.keysym == 'Up':
            self.rotate()
        elif event.keysym == 'Shift_L':
            self.hold_current_piece()
        elif event.keysym == 'space':
            self.hard_drop()
        self.draw()


    def show_end_screen(self, message):
        # Stop game music and play game over sound
        pygame.mixer.music.stop()
        self.gameover_music.play(loops=0)
        
        # Clear the window
        self.clear_window()

        # Add final score to history with timestamp
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.score_history.insert(self.score, current_time)
        self.save_local_data()  # Save to local file

        # Load and set the background image
        bg_image = Image.open("go_bg.png")
        bg_image = bg_image.resize((self.root.winfo_screenwidth(), self.root.winfo_screenheight()), Image.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(bg_image)

        bg_label = tk.Label(self.root, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # Create a container frame to hold the message and buttons
        container = tk.Frame(self.root, bg="#04143f", width=80)
        container.place(relx=0.15, rely=0.60, anchor='w')

        # Show the game over message with large, bold white text
        message_label = tk.Label(container, text=message, font=('Lucida Sans Typewriter', 36, "bold"), fg="white", bg="#04143f")
        message_label.pack(pady=(20, 40))

        # Show final score
        score_label = tk.Label(container, text=f"Final Score: {self.score}", font=('Lucida Sans Typewriter', 24, "bold"), fg="#ffd369", bg="#04143f")
        score_label.pack(pady=(0, 20))

        # Create a frame to hold the buttons side by side
        btn_frame = tk.Frame(container, bg="#04143f")
        btn_frame.pack()

        # Style for accept button
        accept_style = {
            "font": ("Helvetica", 14, "bold"),
            "bg": "#04143f",  # Match container background
            "fg": "#ffd369",  # Match text color
            "activebackground": "#1a1f5a",  # Slightly lighter for hover effect
            "activeforeground": "#ffd369",
            "bd": 0,
            "relief": "flat",
            "width": 12,
            "height": 2,
            "cursor": "hand2"
        }

        # Style for decline button
        decline_style = {
            "font": ("Helvetica", 14, "bold"),
            "bg": "#04143f",  # Match container background
            "fg": "#ffd369",  # Match text color
            "activebackground": "#1a1f5a",  # Slightly lighter for hover effect
            "activeforeground": "#ffd369",
            "bd": 0,
            "relief": "flat",
            "width": 12,
            "height": 2,
            "cursor": "hand2"
        }

        # Position parameters (adjust these values as needed)
        position = {
            "relx": 0.15,  # Horizontal position (0.0 to 1.0)
            "rely": 0.75,  # Vertical position (0.0 to 1.0)
            "anchor": "w",  # Anchor point ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'center')
            "padx": 15,    # Horizontal padding between buttons
            "pady": 10     # Vertical padding
        }

        # Rematch button
        rematch_btn = tk.Button(btn_frame, text="🔄 Rematch", command=self.request_rematch, **accept_style)
        rematch_btn.pack(side='left', padx=position['padx'], pady=position['pady'])

        # Exit Game button
        exit_btn = tk.Button(btn_frame, text="❌ Exit Game", command=self.root.destroy, **decline_style)
        exit_btn.pack(side='left', padx=position['padx'], pady=position['pady'])

        # Add rematch status label
        self.rematch_status = tk.Label(container, text="", font=('Helvetica', 14), fg="#ffd369", bg="#04143f")
        self.rematch_status.pack(pady=(20, 0))

        # Add Leaderboard button with enhanced styling
        leaderboard_btn = tk.Button(container, 
                                  text="🏆 Leaderboard", 
                                  command=self.show_lobby_leaderboard,
                                  font=('Helvetica', 18),
                                  bg="#ffd369",
                                  fg="#222831",
                                  activebackground="#e6c25a",
                                  activeforeground="#222831",
                                  bd=0,
                                  relief="flat",
                                  width=15,
                                  height=2,
                                  cursor="hand2")
        leaderboard_btn.pack(pady=(20, 0))

    def request_rematch(self):
        try:
            self.conn.send(json.dumps({"type": "rematch_request"}).encode() + b'\n')
            self.rematch_status.config(text="Waiting for opponent...")
        except Exception as e:
            print(f"Failed to send rematch request: {e}")

    def back_to_lobby(self):
        self.lobby_ui()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_system_message(self, message):
        self.system_label.config(text=f"SYSTEM: {message}")

    def binary_search_player(self, sorted_players, target_name):
        """Binary search for a player name in sorted (name, score) list"""
        low, high = 0, len(sorted_players) - 1
        while low <= high:
            mid = (low + high) // 2
            mid_name = sorted_players[mid][0].lower()
            if mid_name == target_name.lower():
                return mid  # Found
            elif mid_name < target_name.lower():
                low = mid + 1
            else:
                high = mid - 1
        return -1  # Not found

    def show_lobby_leaderboard(self):
        """Show the local leaderboard in a popup window with enhanced design"""
        popup = tk.Toplevel(self.root)
        popup.title("Local Leaderboard")
        popup.geometry("400x500")
        popup.configure(bg="#222831")

        # Title with modern styling
        title_frame = tk.Frame(popup, bg="#222831", pady=20)
        title_frame.pack(fill='x')
        
        title = tk.Label(title_frame, 
                        text="🏆 LEADERBOARD", 
                        font=("Helvetica", 24, "bold"),
                        bg="#222831", 
                        fg="#ffd369")
        title.pack()

        # Create frame for the list with scrollbar
        list_frame = tk.Frame(popup, bg="#222831", padx=20, pady=10)
        list_frame.pack(fill="both", expand=True)

        # Scrollbar with custom styling
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        # Leaderboard list with enhanced styling
        leaderboard_list = tk.Listbox(list_frame, 
                                    yscrollcommand=scrollbar.set,
                                    bg="#393e46", 
                                    fg="#ffd369",
                                    font=("Courier New", 14),  # Using Courier New for perfect alignment
                                    selectmode="none",
                                    height=15,
                                    bd=0,
                                    highlightthickness=0)
        leaderboard_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=leaderboard_list.yview)

        # Get and sort the leaderboard data
        player_scores = []
        for player_name, scores in self.leaderboard_data.items():
            if scores:  # If player has any scores
                highest_score = max(score['score'] for score in scores)
                player_scores.append((player_name, highest_score))

        # Sort players by highest score in descending order
        sorted_players = sorted(player_scores, key=lambda x: x[1], reverse=True)

        # Populate the list with sorted leaderboard data
        for i, (player_name, highest_score) in enumerate(sorted_players, 1):
            # Add rank number with medal emoji for top 3
            rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i:2d}."
            
            # Format the entry with fixed-width spacing
            # Using a format that ensures perfect alignment
            entry = f"{rank} {player_name:15} {highest_score:8,}"
            leaderboard_list.insert(tk.END, entry)
            
            # Add a subtle separator line between entries
            if i < len(sorted_players):
                separator = "─" * 35  # Fixed width separator
                leaderboard_list.insert(tk.END, separator)

        # Close button with modern styling
        close_btn = tk.Button(popup, 
                            text="Close", 
                            command=popup.destroy,
                            font=("Helvetica", 14, "bold"),
                            bg="#ffd369",
                            fg="#222831",
                            activebackground="#e6c25a",
                            activeforeground="#222831",
                            bd=0,
                            relief="flat",
                            width=15,
                            height=3,
                            cursor="hand2")
        close_btn.pack(pady=20)

        # Make popup modal
        popup.transient(self.root)
        popup.grab_set()
        self.root.wait_window(popup)

    def accept_rematch(self):
        try:
            self.conn.send(json.dumps({"type": "rematch_accepted"}).encode() + b'\n')
            self.rematch_status.config(text="")
            # Clear the window and show the start button page
            self.clear_window()
            self.lobby_ui()
        except Exception as e:
            print(f"Failed to accept rematch: {e}")

    def decline_rematch(self):
        self.rematch_status.config(text="")

if __name__ == "__main__":
    try:
        client = TetrisClient()
    except Exception as e:
        print(f"Error starting game: {e}")
        messagebox.showerror("Error", "Failed to start game. Please check your connection and try again.")