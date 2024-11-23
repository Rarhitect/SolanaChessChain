from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from mock_data_generator import generate_mock_data
from apply_move import apply_move, InvalidMoveException
from pydantic import BaseModel
from supabase import create_client, Client
import uuid
from typing import Dict, List, Optional
import chess
import os
import dotenv

dotenv.load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print("Application is starting up...")
    max_players = 100
    max_matches = 200

    num_players = 50
    num_matches = 100

    if num_players > max_players:
        num_players = max_players

    if num_matches > max_matches:
        num_matches = max_matches

    generate_mock_data(num_players=num_players, num_matches=num_matches)

    yield
    # Code to run on shutdown
    print("Application is shutting down...")

app = FastAPI(lifespan=lifespan)

# origins = [
#     "https://solanachesschain.vercel.app"
# ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class User(BaseModel):
    username: str
    rating: int

class GameRequest(BaseModel):
    user_id: str

class CreateGameRequest(BaseModel):
    user_id: str
    bet: float

class GameInfo(BaseModel):
    game_id: str
    creator_id: str
    creator_username: str
    creator_rating: int
    bet: float

class JoinGameRequest(BaseModel):
    user_id: str
    game_id: str

class CompleteGameRequest(BaseModel):
    game_id: str
    winner_id: Optional[str]
    is_draw: bool = False

class SpectateGameRequest(BaseModel):
    user_id: str
    game_id: str

class MoveRequest(BaseModel):
    game_id: str
    player_id: str
    move: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.game_spectators: Dict[str, List[str]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)
        for spectators in self.game_spectators.values():
            if user_id in spectators:
                spectators.remove(user_id)

    async def send_personal_message(self, user_id: str, message):
        websocket = self.active_connections.get(user_id)
        if websocket:
            if isinstance(message, dict):
                await websocket.send_json(message)
            else:
                await websocket.send_text(message)

    async def broadcast_to_game(self, game_id:str, message: str):
        spectators = self.game_spectators.get(game_id, [])
        for user_id in spectators:
            await self.send_personal_message(user_id, message)
        game_response = supabase.table('games').select('*').eq('game_id', game_id).execute()
        if game_response.data:
            game = game_response.data[0]
            player1_id = game.get('player1_id')
            player2_id = game.get('player2_id')
            if player1_id:
                await self.send_personal_message(player1_id, message)
            if player2_id:
                await self.send_personal_message(player2_id, message)

manager = ConnectionManager()

# Connecting WebSocket:
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)

# User registration:
@app.post('/register')
async def register_user(user: User):
    user_id = str(uuid.uuid4())
    response = supabase.table('users').insert({
        'id': user_id,
        'username': user.username,
        'rating': user.rating,
        'status': 'online'
    }).execute()

    if response.error:
        raise HTTPException(status_code=400, detail=response.error.message)
    
    return {'user_id': user_id}

# User creates a game:
@app.post('/create_game')
async def create_game(request: CreateGameRequest):
    user_id = request.user_id
    bet = request.bet

    # Check if user exists:
    user_response = supabase.table('users').select('*').eq('id', user_id).execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail='User not found')
    
    user = user_response.data[0]

    # Create a game:
    game_id = str(uuid.uuid4())
    game_response = supabase.table('games').insert({
        'game_id': game_id,
        'player1_id': user_id,
        'status': 'pending',
        'bet': bet,
    }).execute()

    if game_response.error:
        raise HTTPException(status_code=400, detail=game_response.error.message)
    
    supabase.table('users').update({'status': 'waiting'}).eq('id', user_id).execute()

    for uid in manager.active_connections.keys():
        if uid != user_id:
            await manager.send_personal_message(uid, f"New game available with bet {bet}")
    
    return {'message': 'Game created successfully', 'game_id': game_id, 'creator': user['username'], 'bet': bet}

# Get a list of legible games:
@app.get('/list_games')
async def list_games(request:GameRequest):
    user_id = request.user_id

    # Check if user exists:
    user_response = supabase.table('users').select('*').eq('id', user_id).execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail='User not found')
    
    user = user_response.data[0]
    user_rating = user['rating']

    games_response = supabase.table('games').select('*').eq('status', 'pending').neq('player1_id', user_id).execute()
    games = games_response.data

    game_list = []
    for game in games:
        creator_response = supabase.table('users').select('*').eq('id', game['player1_id']).execute()
        if not creator_response.data:
            continue

        creator = creator_response.data[0]
        creator_rating = creator['rating']

        if abs(creator_rating - user_rating) <= 100:
            game_info = GameInfo(
                game_id=game['game_id'],
                creator_id=creator['id'],
                creator_username=creator['username'],
                creator_rating=creator_rating,
                bet=game['bet']
            )
            game_list.append(game_info)

        if not game_list:
            return {'message': 'No games available now'}
        
        return game_list
    
# Joining game:
@app.post('/join_game')
async def join_game(request: JoinGameRequest):
    user_id = request.user_id
    game_id = request.game_id

    user_response = supabase.table('games').select('*').eq('id', user_id).execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail='User not found')
    
    user = user_response.data[0]
    
    game_response = supabase.table('games').select('*').eq('game_id', game_id).execute()
    if not game_response.data:
        raise HTTPException(status_code=404, detail='Game not found')
    
    game = game_response.data[0]

    if game['status'] != 'pending':
        raise HTTPException(status_code=400, detail='Game is not available')
    
    update_response = supabase.table('games').update({
        'player2_id': user_id,
        'status': 'in_progress'
    }).eq('game_id', game_id).execute()

    if update_response.error:
        raise HTTPException(status_code=400, detail=update_response.error.message)
    
    users_update_response = supabase.table('users').update({'status': 'in_game'}).in_('id', [user_id, game['player1_id']]).execute()
    if users_update_response.error:
        raise HTTPException(status_code=500, detail='Failed to update users status')
    
    board = chess.Board()
    initial_game_state = {
        'board': board.fen(),
        'turn': game['player1_id'],
        'history': []
    }

    supabase.table('games').update({
        'game_state': initial_game_state
    }).eq('game_id', game_id).execute()

    await manager.broadcast_to_game(game_id, {
        'type': 'game_started',
        'game_id': game_id,
        'game_state': initial_game_state
    })

    creator_id = game['player1_id']
    await manager.send_personal_message(creator_id, f"{user['username']} has joined your game.")

    return {'message': 'Game joined successfully', 'game_id': game_id}

# Finish game:
@app.post('/complete_game')
async def complete_game(request: CompleteGameRequest):
    game_id = request.game_id
    winner_id = request.winner_id
    is_draw = request.is_draw

    game_response = supabase.table('games').select('*').eq('game_id', game_id).execute()
    if not game_response.data:
        raise HTTPException(status_code=404, detail='Game not found')
    
    game = game_response.data[0]

    if game['status'] != 'in_progress':
        raise HTTPException(status_code=400, detail='Game is not in progress')
    
    player1_id = game['player1_id']
    player2_id = game['player2_id']

    if winner_id not in [player1_id, player2_id]:
        raise HTTPException(status_code=400, detail='Invalid winner id')
    
    players_response = supabase.table('users').select('*').in_('id', [player1_id, player2_id]).execute()
    if len(players_response.data) != 2:
        raise HTTPException(status_code=404, detail='Players not found')
    
    player1 = next((p for p in players_response.data if p['id'] == player1_id), None)
    player2 = next((p for p in players_response.data if p['id'] == player2_id), None)

    rating1 = player1['rating']
    rating2 = player2['rating']

    expected_score1 = 1 / (1 + 10 ** ((rating2 - rating1) / 400))
    expected_score2 = 1 / (1 + 10 ** ((rating1 - rating2) / 400))

    k = 32

    if is_draw:
        score1 = 0.5
        score2 = 0.5

        supabase.table('users').update({'draws': player1['draws'] + 1}).eq('id', player1_id).execute()
        supabase.table('users').update({'draws': player2['draws'] + 1}).eq('id', player2_id).execute()
    else:
        if winner_id == player1_id:
            score1 = 1
            score2 = 0

            supabase.table('users').update({'wins': player1['wins'] + 1}).eq('id', player1_id).execute()
            supabase.table('users').update({'losses': player2['losses'] + 1}).eq('id', player2_id).execute()
        elif winner_id == player2_id:
            score1 = 0
            score2 = 1

            supabase.table('users').update({'losses': player1['losses'] + 1}).eq('id', player1_id).execute()
            supabase.table('users').update({'wins': player2['wins'] + 1}).eq('id', player2_id).execute()
        else:
            raise HTTPException(status_code=400, detail='Winner ID is invalid')

    new_rating1 = rating1 + k * (score1 - expected_score1)
    new_rating2 = rating2 + k * (score2 - expected_score2)

    supabase.table('users').update({'rating': int(new_rating1), 'status': 'online'}).eq('id', player1_id).execute()
    supabase.table('users').update({'rating': int(new_rating2), 'status': 'online'}).eq('id', player2_id).execute()

    supabase.table('games').update({'status': 'completed'}).eq('game_id', game_id).execute()

    await manager.send_personal_message(player1_id, f"Game completed. Your new rating is {int(new_rating1)}")
    await manager.send_personal_message(player2_id, f"Game completed. Your new rating is {int(new_rating2)}")

    return {'message': 'Game completed successfully', 'new_ratings': {
        player1['username']: int(new_rating1),
        player2['username']: int(new_rating2)
    }}

# Get the Leaderboard:
@app.get('/leaderboard')
async def leaderboard(limit: int = 100):
    users_response = supabase.table('users').select('username, rating, wins, losses, draws').order('rating', desc=True).limit(limit).execute()

    if users_response.error:
        raise HTTPException(status_code=500, detail='Failed to retrieve leaderboard')

    users = users_response.data

    leaderboard = []
    for user in users:
        total_games = user['wins'] + user['losses'] + user['draws']
        win_percentage = (user['wins'] / total_games * 100) if total_games > 0 else 0

        leaderboard.append({
            'username': user['username'],
            'rating': user['rating'],
            'wins': user['wins'],
            'losses': user['losses'],
            'draws': user['draws'],
            'win_percentage': round(win_percentage, 2)
        })

    return {'leaderboard': leaderboard}

# Get game information:
@app.get('/games/{game_id}')
async def get_game(game_id: str):
    game_response = supabase.table('games').select('*').eq('game_id', game_id).execute()
    if not game_response.data:
        raise HTTPException(status_code=404, detail='Game not found')
    
    game = game_response.data[0]
    return game

# Spectate a game:
@app.post('/spectate_game')
async def spectate_game(request: SpectateGameRequest):
    user_id = request.user_id
    game_id = request.game_id

    user_response = supabase.table('users').select('*').eq('id', user_id).execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail='User not found')

    game_response = supabase.table('games').select('*').eq('game_id', game_id).execute()
    if not game_response.data:
        raise HTTPException(status_code=404, detail='Game not found')
    
    game = game_response.data[0]
    if game['status'] != 'in_progress':
        raise HTTPException(status_code=400, detail='Game is not in progress')
    
    supabase.table('spectators').insert({
        'game_id': game_id,
        'user_id': user_id
    }).execute()

    if game_id not in manager.game_spectators:
        manager.game_spectators[game_id] = []
    if user_id not in manager.game_spectators[game_id]:
        manager.game_spectators[game_id].append(user_id)

    await manager.broadcast_to_game(game_id, f"User {user_id} is now spectating the game.")

    return {'message': f"You are now spectating the game {game_id}"}

# Leave spectating mdoe:
@app.post('/leave_spectate')
async def leave_spectate(request: SpectateGameRequest):
    user_id = request.user_id
    game_id = request.game_id

    supabase.table('spectators').delete().eq('game_id', game_id).eq('user_id', user_id).execute()

    if game_id in manager.game_spectators:
        if user_id in manager.game_spectators[game_id]:
            manager.game_spectators[game_id].remove(user_id)

    await manager.broadcast_to_game(game_id, f"User {user_id} has stopped spectating the game.")

    return {'message': f"You have left spectating the game {game_id}"}

@app.post('/make_move')
async def make_move(request: MoveRequest):
    game_id = request.game_id
    player_id = request.player_id
    move = request.move

    move = chess.Move.from_uci(move)

    game_response = supabase.table('games').select('*').eq('game_id', game_id).execute()
    if not game_response.data:
        raise HTTPException(status_code=404, detail='Game not found')
    game = game_response.data[0]

    if game['status'] != 'in_progress':
        raise HTTPException(status_code=400, detail='Game is not in progress')
    
    player1_id = game.get('player1_id')
    player2_id = game.get('player2_id')
    if player_id not in [player1_id, player2_id]:
        raise HTTPException(status_code=403, detail='You are not a participant of this game')

    game_state = game.get('game_state')
    if not game_state:
        raise HTTPException(status_code=400, detail='Game state is not initialized')

    current_turn = game_state.get('turn')
    if current_turn != player_id:
        raise HTTPException(status_code=400, detail='It is not your turn')

    try:
        new_game_state = apply_move(game_state, move, player_id, player1_id, player2_id)
        other_player = player1_id if player_id == player2_id else player2_id
        await manager.send_personal_message(other_player, f"Move {move} by {player_id} made successfully.")
    except InvalidMoveException as e:
        raise HTTPException(status_code=400, detail=str(e))

    update_response = supabase.table('games').update({
        'game_state': new_game_state
    }).eq('game_id', game_id).execute()

    if update_response.error:
        raise HTTPException(status_code=500, detail='Failed to update the game state')

    await manager.broadcast_to_game(game_id, {
        'type': 'move_made',
        'player_id': player_id,
        'move': move,
        'game_state': new_game_state
    })

    return {'message': 'Move made successfully'}

# Get random pending game:
@app.get('/random_game')
async def get_random_game():
    game_response = supabase.table('games').select('*').eq('status', 'pending').limit(1).execute()
    if not game_response.data:
        raise HTTPException(status_code=404, detail='No pending games found')
    
    game = game_response.data[0]
    return game