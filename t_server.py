# Import required libraries
import socket
import threading
import json
import heapq  # For the priority queue implementation

# Server configuration
HOST = '192.168.251.73'  # Bind to all interfaces
PORT = 5555

# Global data structures for managing game state
clients = []  # List of connected clients with their connection info and usernames
ready_status = {}  # Dictionary tracking whether each player is ready
lock = threading.Lock()  # Thread safety for shared data access
rematch_requests = {}  # Dictionary tracking rematch requests

# Priority queue for managing ready players (using a heap)
# This ensures fair matching of players based on their readiness
priority_queue = []  # A min-heap based priority queue (priority queue by readiness)

def broadcast(message, sender_conn=None):
    """
    Broadcast a message to all connected clients except the sender
    Args:
        message: The message to broadcast
        sender_conn: Optional connection to exclude from broadcast
    """
    with lock:
        for client in clients:
            conn = client['conn']
            if conn != sender_conn:
                try:
                    conn.send((json.dumps(message) + '\n').encode())
                except:
                    pass

def notify_opponent_left(disconnected_username):
    """
    Notify remaining players when someone disconnects
    Args:
        disconnected_username: Username of the player who disconnected
    """
    for client in clients:
        if client['username'] != disconnected_username:
            try:
                client['conn'].send(json.dumps({
                    'type': 'system',
                    'message': f'Opponent {disconnected_username} has left the game.'
                }).encode() + b'\n')
            except:
                pass

def handle_client(conn, addr):
    """
    Handle communication with a connected client
    Args:
        conn: Client socket connection
        addr: Client address
    """
    global clients, ready_status, priority_queue, rematch_requests
    try:
        # Get username from client
        username = conn.recv(1024).decode()
        print(f"[{username}] Connected from {addr}")
        
        # Add client to tracking structures
        with lock:
            clients.append({'conn': conn, 'addr': addr, 'username': username})
            ready_status[username] = False
        update_lobby()

        # Add player to priority queue with initial readiness (0)
        heapq.heappush(priority_queue, (0, username))

        # Main message handling loop
        while True:
            try:
                data = conn.recv(2048)
                if not data:
                    print(f"[{username}] Disconnected (no data)")
                    break
                    
                msg = json.loads(data.decode())
                print(f"[{username}] received: {msg['type']}")

                # Handle different message types
                if msg['type'] == 'ready':
                    # Update player's ready status
                    with lock:
                        ready_status[username] = msg['ready']
                    update_lobby()

                    # Update priority queue with new readiness status
                    with lock:
                        priority_queue = [(status, user) for status, user in priority_queue if user != username]
                        heapq.heapify(priority_queue)
                        heapq.heappush(priority_queue, (1 if ready_status[username] else 0, username))

                    # Start game if exactly 2 players are ready
                    with lock:
                        if len(clients) == 2 and all(ready_status[c['username']] for c in clients):
                            start_game()

                elif msg['type'] == 'score':
                    # Broadcast score updates to other players
                    broadcast({'type': 'score', 'value': msg['value']}, sender_conn=conn)
                
                elif msg['type'] == 'board':
                    # Broadcast board state to other players
                    broadcast({'type': 'board', 'board': msg['board']}, sender_conn=conn)
                
                elif msg['type'] == 'lose':
                    print(f"[{username}] Lost the game")
                    # Handle game over when a player loses
                    with lock:
                        loser_conn = conn
                        loser_name = None
                        winner_conn = None
                        winner_name = None

                        # Find loser and winner information
                        for client in clients:
                            if client['conn'] == loser_conn:
                                loser_name = client['username']
                                break

                        for client in clients:
                            if client['conn'] != loser_conn:
                                winner_conn = client['conn']
                                winner_name = client['username']
                                break

                    # Send game over messages to both players
                    try:
                        # Send lose message to loser
                        loser_conn.send((json.dumps({
                            'type': 'game_over',
                            'result': 'lose',
                            'winner': winner_name
                        }) + '\n').encode())
                        print(f"[{username}] Sent lose message to loser")
                    except Exception as e:
                        print(f"[{username}] Failed to send lose message: {e}")

                    if winner_conn:
                        try:
                            # Send win message to winner
                            winner_conn.send((json.dumps({
                                'type': 'game_over',
                                'result': 'win',
                                'winner': winner_name
                            }) + '\n').encode())
                            print(f"[{username}] Sent win message to winner")
                        except Exception as e:
                            print(f"[{username}] Failed to send win message: {e}")

                elif msg['type'] == 'chat':
                    # Handle chat messages
                    broadcast({
                        'type': 'chat',
                        'from': username,
                        'message': msg['message']
                    })
                
                elif msg['type'] == 'request_lobby':
                    # Send updated lobby information
                    update_lobby()

                elif msg['type'] == 'rematch_request':
                    print(f"[{username}] Requested rematch")
                    # Handle rematch request
                    with lock:
                        # Find opponent
                        opponent_conn = None
                        opponent_name = None
                        for client in clients:
                            if client['conn'] != conn:
                                opponent_conn = client['conn']
                                opponent_name = client['username']
                                break
                        
                        if opponent_conn:
                            # Store rematch request
                            rematch_requests[username] = opponent_name
                            # Send rematch request to opponent
                            try:
                                opponent_conn.send((json.dumps({
                                    'type': 'rematch_request',
                                    'from': username
                                }) + '\n').encode())
                            except Exception as e:
                                print(f"[{username}] Failed to send rematch request: {e}")

                elif msg['type'] == 'rematch_accepted':
                    print(f"[{username}] Accepted rematch")
                    # Handle rematch acceptance
                    with lock:
                        # Find opponent
                        opponent_conn = None
                        opponent_name = None
                        for client in clients:
                            if client['conn'] != conn:
                                opponent_conn = client['conn']
                                opponent_name = client['username']
                                break
                        
                        if opponent_conn:
                            # Clear rematch requests for both players
                            if username in rematch_requests:
                                del rematch_requests[username]
                            if opponent_name in rematch_requests:
                                del rematch_requests[opponent_name]
                            
                            # Send rematch accepted to both players
                            try:
                                opponent_conn.send((json.dumps({
                                    'type': 'rematch_accepted'
                                }) + '\n').encode())
                                conn.send((json.dumps({
                                    'type': 'rematch_accepted'
                                }) + '\n').encode())
                                
                                # Send start message to both players
                                opponent_conn.send((json.dumps({
                                    'type': 'start'
                                }) + '\n').encode())
                                conn.send((json.dumps({
                                    'type': 'start'
                                }) + '\n').encode())
                            except Exception as e:
                                print(f"[{username}] Failed to send rematch accepted: {e}")

            except json.JSONDecodeError as e:
                print(f"[{username}] Invalid JSON received: {e}")
                continue
            except Exception as e:
                print(f"[{username}] Error processing message: {e}")
                continue

    except Exception as e:
        print(f"[{username}] Error handling client {addr}: {e}")
    finally:
        # Cleanup when client disconnects
        print(f"[{username}] Disconnecting")
        with lock:
            clients[:] = [c for c in clients if c['conn'] != conn]
            if username in ready_status:
                del ready_status[username]
            priority_queue[:] = [(status, user) for status, user in priority_queue if user != username]
            heapq.heapify(priority_queue)
            # Clean up any rematch requests involving this player
            rematch_requests = {k: v for k, v in rematch_requests.items() 
                              if k != username and v != username}

        # Notify other players about disconnection
        notify_opponent_left(username)
        conn.close()
        update_lobby()

def update_lobby():
    """
    Send updated lobby information to all clients
    Includes player list and their ready status
    """
    with lock:
        sorted_players = [{'name': user, 'ready': ready_status.get(user, False)} for _, user in sorted(priority_queue)]
        message = {'type': 'lobby', 'players': sorted_players}
        for client in clients:
            try:
                client['conn'].send((json.dumps(message) + '\n').encode())
            except:
                pass

def start_game():
    """
    Notify all clients to start the game
    Sends start message to all connected players
    """
    message = {'type': 'start'}
    for client in clients:
        try:
            client['conn'].send((json.dumps(message) + '\n').encode())
        except:
            pass

def start_server():
    """
    Initialize and start the game server
    Listens for incoming connections and spawns handler threads
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    server_ip = socket.gethostbyname(socket.gethostname())
    print(f"Server listening on {server_ip}:{PORT}")
    
    # Main server loop
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server() 