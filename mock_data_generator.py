import random
import string
import uuid
from supabase import create_client, Client
import chess


def generate_random_username(length=8):
    letters = string.ascii_lowercase
    return 'mock_' + ''.join(random.choice(letters) for _ in range(length))

def generate_random_rating(min_rating=800, max_rating=2400):
    return random.randint(min_rating, max_rating)

def create_mock_player(supabase_client):
    username = generate_random_username()
    rating = generate_random_rating()
    user_id = str(uuid.uuid4())

    wins = random.randint(0, 100)
    losses = random.randint(0, 100)
    draws = random.randint(0, 50)

    try:
        response = supabase_client.table('users').insert({
            'id': user_id,
            'username': username,
            'rating': rating,
            'status': 'online',
            'wins': wins,
            'losses': losses,
            'draws': draws
        }).execute()
    except Exception as e:
        print(f"Error creating user {username}: {e}")
        return None
    return user_id

def generate_mock_players(supabase_client, num_players=50):
    user_ids = []
    for _ in range(num_players):
        user_id = create_mock_player(supabase_client)
        user_ids.append(user_id)
        print(f"User {user_id} created")
    return user_ids

def create_mock_match(supabase_client, player1_id, player2_id):
    game_id = str(uuid.uuid4())
    bet = random.randint(10, 1000)
    
    board = chess.Board()
    initial_game_state = {
        'board': board.fen(),
        'turn': player1_id,
        'history': []
    }

    try:
        response = supabase_client.table('games').insert({
            'game_id': game_id,
            'player1_id': player1_id,
            'player2_id': player2_id,
            'status': 'in_progress',
            'bet': bet
        }).execute()
    except Exception as e:
        print(f"Error creating match {game_id}: {e}")
        return None

    return game_id

# def complete_mock_match(supabase_client, game_id, player1_id, player2_id):
#     result = random.choice(['player1_win', 'player2_win', 'draw'])
    
#     try:
#         players_response = supabase_client.table('games').select('*').eq('game_id', game_id).execute()
#     except:
#         print(f"Error retrieving game {game_id}")
#         return

#     player1 = next((p for p in players_response.data if p['id'] == player1_id), None)
#     player2 = next((p for p in players_response.data if p['id'] == player2_id), None)

#     rating1 = player1['rating']
#     rating2 = player2['rating']

#     expected_score1 = 1 / (1 + 10 ** ((rating2 - rating1) / 400))
#     expected_score2 = 1 / (1 + 10 ** ((rating1 - rating2) / 400))

#     k = 32

#     if result == 'draw':
#         score1 = 0.5
#         score2 = 0.5

#         new_rating1 = rating1 + k * (score1 - expected_score1)
#         new_rating2 = rating2 + k * (score2 - expected_score2)

#         supabase_client.table('users').update({
#             'draws': player1['draws'] + 1,
#             'rating': int(new_rating1)
#         }).eq('id', player1_id).execute()

#         supabase_client.table('users').update({
#             'draws': player2['draws'] + 1,
#             'rating': int(new_rating2)
#         }).eq('id', player2_id).execute()
#     else:
#         if result == 'player1_win':
#             winner_id = player1_id
#             loser_id = player2_id
#             score1 = 1
#             score2 = 0
#         else:
#             winner_id = player2_id
#             loser_id = player1_id
#             score1 = 0
#             score2 = 1

#         new_rating1 = rating1 + k * (score1 - expected_score1)
#         new_rating2 = rating2 + k * (score2 - expected_score2)

#         supabase_client.table('users').update({
#             'wins': player1['wins'] + (1 if winner_id == player1_id else 0),
#             'losses': player1['losses'] + (1 if loser_id == player1_id else 0),
#             'rating': int(new_rating1)
#         }).eq('id', player1_id).execute()

#         supabase_client.table('users').update({
#             'wins': player2['wins'] + (1 if winner_id == player2_id else 0),
#             'losses': player2['losses'] + (1 if loser_id == player2_id else 0),
#             'rating': int(new_rating2)
#         }).eq('id', player2_id).execute()

#     supabase_client.table('games').update({'status': 'completed'}).eq('game_id', game_id).execute()

#     print(f"Completed game {game_id} with result: {result}")

# def generate_mock_matches(supabase_client, user_ids, num_matches=100):
#     for _ in range(num_matches):
#         player1_id, player2_id = random.sample(user_ids, 2)
#         match_id = create_mock_match(supabase_client, player1_id, player2_id)
#         print(f"Match {match_id} between {player1_id} and {player2_id} started")
#         complete_mock_match(supabase_client, match_id, player1_id, player2_id)
#         print(f"Match {match_id} between {player1_id} and {player2_id} completed")

def generate_in_progress_matches(supabase_client, user_ids, num_matches=100):
    for _ in range(num_matches):
        player1_id, player2_id = random.sample(user_ids, 2)
        match_id = create_mock_match(supabase_client, player1_id, player2_id)
        supabase_client.table('users').update({'status': 'playing'}).in_('id', [player1_id, player2_id]).execute()
        print(f"Match {match_id} between {player1_id} and {player2_id} started")

def generate_pending_matches(supabase_client, user_ids, num_matches=100):
    for _ in range(num_matches):
        player_id = random.sample(user_ids, 1)[0]
        try:
            game_id = str(uuid.uuid4())
            bet = random.randint(10, 1000)
            supabase_client.table('games').insert({
                'game_id': game_id,
                'player1_id': player_id,
                'status': 'pending',
                'bet': bet
            }).execute()
            print(f"Pending game {game_id} is created by {player_id}")
            supabase_client.table('users').update({'status': 'waiting'}).eq('id', player_id).execute()
        except Exception as e:
            print(f"Error creating match: {e}")
            return None

def generate_mock_data(num_players=50, num_matches=100):
    SUPABASE_URL = 'https://bvyhuytnakbmjlbdbybz.supabase.co'
    SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ2eWh1eXRuYWtibWpsYmRieWJ6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzIzNTUyMTIsImV4cCI6MjA0NzkzMTIxMn0.cjQMDVTTJfBjOgiKx4Klhet_iIEKIq6FdgJu479h-sk'
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    user_ids = generate_mock_players(supabase_client, num_players=num_players)

    # generate_mock_matches(supabase_client, user_ids, num_matches=num_matches)

    generate_in_progress_matches(supabase_client, user_ids, num_matches=10)

    generate_pending_matches(supabase_client, user_ids, num_matches=10)