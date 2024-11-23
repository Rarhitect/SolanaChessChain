import chess

class InvalidMoveException(Exception):
    pass

def apply_move(game_state, move, player_id, player1_id, player2_id):
    board_fen = game_state.get('board')
    history = game_state.get('history', [])

    if not board_fen:
        board = chess.Board()
    else:
        board = chess.Board(board_fen)

    if player_id == player1_id:
        player_color = chess.WHITE
    else:
        player_color = chess.BLACK

    if board.turn != player_color:
        raise InvalidMoveException('It is not your turn')

    try:
        chess_move = board.parse_san(move)
    except ValueError:
        raise InvalidMoveException('Invalid move notation')

    if chess_move not in board.legal_moves:
        raise InvalidMoveException('Illegal move')

    board.push(chess_move)

    next_turn = player1_id if player_id == player2_id else player2_id

    new_game_state = {
        'board': board.fen(),
        'turn': next_turn,
        'history': history + [move]
    }

    return new_game_state