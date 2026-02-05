# Tetris Game 🎮

A classic Tetris game implementation with multiplayer support built in Python.

## Features
- Classic Tetris gameplay
- Background music and sound effects
- Leaderboard system
- Multiplayer mode (client-server)
- Score tracking

## Requirements
- Python 3.x
- Pygame

## Installation
1. Clone this repository:
```bash
git clone https://github.com/maicode10/Tetris-Game.git
cd Tetris-Game
```

2. Install required packages:
```bash
pip install pygame
```

## How to Play
**Single Player:**
```bash
python t_client.py
```

**Multiplayer:**
1. Start the server:
```bash
python t_server.py
```

2. Run the client:
```bash
python t_client.py
```

## Controls
- **Arrow Keys**: Move pieces left/right/down
- **Up Arrow**: Rotate piece
- **Space**: Drop piece instantly

## Game Rules
- Clear lines by filling rows completely
- Game ends when pieces reach the top
- Score increases with lines cleared

## Screenshots
(Add screenshots of your game here)

## Credits
Created by Maira Lorraine

## License
MIT License
