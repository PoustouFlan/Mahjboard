import json
from flask import Blueprint, render_template, request, redirect, url_for
from .db import get_db
from .logic import calculate_signed_scores, calculate_rating_updates, calculate_display_rating

bp = Blueprint('main', __name__)

def get_full_game_history(limit=None, player_id=None):
    db = get_db()
    if player_id:
        query = '''SELECT g.id, g.timestamp, g.game_type
                   FROM games g JOIN results r ON g.id = r.game_id
                   WHERE r.player_id = ? ORDER BY g.id DESC'''
        params = (player_id,)
    else:
        query = 'SELECT id, timestamp, game_type FROM games ORDER BY id DESC'
        params = ()

    if limit: query += f' LIMIT {limit}'

    games = db.execute(query, params).fetchall()

    structured_games = []
    for g in games:
        results_raw = db.execute('''
            SELECT p.name, p.id as player_id, r.raw_score, r.net_score,
                   r.rank_change_general, r.rank_change_mode,
                   r.rating_change_general, r.rating_change_mode  -- <--- ADD THESE
            FROM results r JOIN players p ON r.player_id = p.id
            WHERE r.game_id = ? ORDER BY r.net_score DESC
        ''', (g['id'],)).fetchall()

        target = sum(r['raw_score'] for r in results_raw) / len(results_raw) if results_raw else 0

        results = []
        for r in results_raw:
            r_dict = dict(r)
            # Reconstitution de l'uma : Net = (Raw - Target)/1000 + Uma
            r_dict['uma'] = r_dict['net_score'] - (r_dict['raw_score'] - target) / 1000.0
            results.append(r_dict)

        structured_games.append({
            'id': g['id'],
            'timestamp': g['timestamp'],
            'type': g['game_type'],
            'results': results
        })
    return structured_games


@bp.route('/')
def index():
    print("DEBUG: Entering index() route")
    db = get_db()
    players_raw = db.execute("SELECT * FROM players").fetchall()

    players_processed = []
    for p in players_raw:
        d_gen = calculate_display_rating(p['rating'], p['games_played'])
        d_4p = calculate_display_rating(p['rating_4p'], p['games_4p'])
        d_3p = calculate_display_rating(p['rating_3p'], p['games_3p'])

        players_processed.append({
            'id': p['id'], 'name': p['name'],
            'display_gen': d_gen, 'games_gen': p['games_played'],
            'display_4p': d_4p,   'games_4p': p['games_4p'],
            'display_3p': d_3p,   'games_3p': p['games_3p']
        })

    players_processed.sort(key=lambda x: x['display_gen'], reverse=True)
    recent_games = get_full_game_history(limit=10)

    top_5 = players_processed[:5]
    assert len(top_5) <= 5, "Top 5 list should not exceed 5 elements"

    games_gen = db.execute('SELECT id FROM games ORDER BY id DESC LIMIT 15').fetchall()
    games_4p = db.execute('SELECT id FROM games WHERE game_type = 4 ORDER BY id DESC LIMIT 15').fetchall()
    games_3p = db.execute('SELECT id FROM games WHERE game_type = 3 ORDER BY id DESC LIMIT 15').fetchall()

    games_gen = list(reversed(games_gen))
    games_4p = list(reversed(games_4p))
    games_3p = list(reversed(games_3p))

    chart_data = {
        'gen': {'labels': [f"#{g['id']}" for g in games_gen], 'datasets': []},
        '4p':  {'labels': [f"#{g['id']}" for g in games_4p], 'datasets': []},
        '3p':  {'labels': [f"#{g['id']}" for g in games_3p], 'datasets': []}
    }

    colors = ['#0d47a1', '#2e7d32', '#ef6c00', '#6a1b9a', '#c62828']

    for i, p in enumerate(top_5):
        pid = p['id']
        p_games = db.execute('''
            SELECT g.id, g.game_type, r.new_rating_general, r.new_rating_mode
            FROM games g
            JOIN results r ON g.id = r.game_id
            WHERE r.player_id = ?
            ORDER BY g.id ASC
        ''', (pid,)).fetchall()

        c_gen, c_4p, c_3p = 0, 0, 0
        history_map = {}

        for row in p_games:
            c_gen += 1
            if row['game_type'] == 4:
                c_4p += 1
                history_map[row['id']] = {
                    'gen': calculate_display_rating(row['new_rating_general'], c_gen),
                    '4p': calculate_display_rating(row['new_rating_mode'], c_4p),
                    'type': 4
                }
            else:
                c_3p += 1
                history_map[row['id']] = {
                    'gen': calculate_display_rating(row['new_rating_general'], c_gen),
                    '3p': calculate_display_rating(row['new_rating_mode'], c_3p),
                    'type': 3
                }

        def get_rating_at(target_gid, mode):
            latest_val = calculate_display_rating(1500, 0)
            for gid in sorted(history_map.keys()):
                if gid > target_gid:
                    break
                if mode == 'gen':
                    latest_val = history_map[gid]['gen']
                elif mode == '4p' and history_map[gid]['type'] == 4:
                    latest_val = history_map[gid]['4p']
                elif mode == '3p' and history_map[gid]['type'] == 3:
                    latest_val = history_map[gid]['3p']
            return latest_val

        data_gen = [get_rating_at(g['id'], 'gen') for g in games_gen]
        data_4p  = [get_rating_at(g['id'], '4p')  for g in games_4p]
        data_3p  = [get_rating_at(g['id'], '3p')  for g in games_3p]

        chart_data['gen']['datasets'].append({'label': p['name'], 'data': data_gen, 'borderColor': colors[i], 'tension': 0.3, 'fill': False})
        chart_data['4p']['datasets'].append({'label': p['name'], 'data': data_4p, 'borderColor': colors[i], 'tension': 0.3, 'fill': False})
        chart_data['3p']['datasets'].append({'label': p['name'], 'data': data_3p, 'borderColor': colors[i], 'tension': 0.3, 'fill': False})

    return render_template('index.html', players=players_processed, games=recent_games, graph_data=chart_data)

@bp.route('/submit', methods=['POST'])
def submit_game():
    db = get_db()

    game_type = int(request.form.get('game_type')) # 3 ou 4

    names = []
    raw_scores = []
    for i in range(1, game_type + 1):
        names.append(request.form.get(f'p{i}_name').strip())
        raw_scores.append(int(request.form.get(f'p{i}_score')))

    player_data = []
    for name in names:
        row = db.execute("SELECT * FROM players WHERE name = ?", (name,)).fetchone()
        if not row:
            cur = db.execute("INSERT INTO players (name) VALUES (?)", (name,))
            db.commit()
            row = db.execute("SELECT * FROM players WHERE id = ?", (cur.lastrowid,)).fetchone()
        player_data.append(row)

    net_scores, umas = calculate_signed_scores(raw_scores)

    # GENERAL Rating Updates
    curr_gen = [p['rating'] for p in player_data]
    updates_gen = calculate_rating_updates(curr_gen, net_scores)

    # MODE SPECIFIC Rating Updates
    col_rating = 'rating_4p' if game_type == 4 else 'rating_3p'
    curr_mode = [p[col_rating] for p in player_data]
    updates_mode = calculate_rating_updates(curr_mode, net_scores)

    cur = db.execute("INSERT INTO games (game_type) VALUES (?)", (game_type,))
    game_id = cur.lastrowid

    col_games = 'games_4p' if game_type == 4 else 'games_3p'

    for i in range(len(player_data)):
        pid = player_data[i]['id']

        # GENERAL
        old_games_gen = player_data[i]['games_played']
        old_disp_gen = calculate_display_rating(player_data[i]['rating'], old_games_gen)
        new_disp_gen = calculate_display_rating(updates_gen[i]['new'], old_games_gen + 1)
        diff_gen = new_disp_gen - old_disp_gen

        # MODE SPECIFIC
        old_games_mode = player_data[i][col_games]
        old_disp_mode = calculate_display_rating(player_data[i][col_rating], old_games_mode)
        new_disp_mode = calculate_display_rating(updates_mode[i]['new'], old_games_mode + 1)
        diff_mode = new_disp_mode - old_disp_mode

        # Update Player Table
        query = f'''
            UPDATE players
            SET rating = ?, games_played = games_played + 1,
                {col_rating} = ?, {col_games} = {col_games} + 1
            WHERE id = ?
        '''
        db.execute(query, (updates_gen[i]['new'], updates_mode[i]['new'], pid))

        # Insert Result
        db.execute('''
            INSERT INTO results (
                game_id, player_id, raw_score, net_score,
                rating_change_general, new_rating_general, rank_change_general,
                rating_change_mode, new_rating_mode, rank_change_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            game_id, pid, raw_scores[i], net_scores[i],
            updates_gen[i]['change'], updates_gen[i]['new'], diff_gen,
            updates_mode[i]['change'], updates_mode[i]['new'], diff_mode
        ))

    db.commit()
    return redirect(url_for('main.index'))

@bp.route('/player/<int:player_id>')
def player_history(player_id):
    db = get_db()
    p = db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    history = get_full_game_history(player_id=player_id)

    # Current Stats
    stats = {
        'gen': {'r': calculate_display_rating(p['rating'], p['games_played']), 'g': p['games_played']},
        '4p':  {'r': calculate_display_rating(p['rating_4p'], p['games_4p']), 'g': p['games_4p']},
        '3p':  {'r': calculate_display_rating(p['rating_3p'], p['games_3p']), 'g': p['games_3p']},
    }

    # Reconstruct History for Graphs
    data = {'labels': [], 'gen': [], '4p': [], '3p': []}
    c_gen, c_4p, c_3p = 0, 0, 0

    for game in reversed(history):
        res = next(r for r in game['results'] if r['player_id'] == player_id)

        c_gen += 1
        if game['type'] == 4: c_4p += 1
        else: c_3p += 1

        # Fetch the snapshots saved in DB
        full_res = db.execute(
            "SELECT new_rating_general, new_rating_mode FROM results WHERE game_id=? AND player_id=?",
            (game['id'], player_id)
        ).fetchone()

        val_gen = calculate_display_rating(full_res['new_rating_general'], c_gen)
        val_mode = calculate_display_rating(full_res['new_rating_mode'], c_4p if game['type']==4 else c_3p)

        data['labels'].append(game['timestamp'])
        data['gen'].append(val_gen)

        if game['type'] == 4:
            data['4p'].append(val_mode)
            last_3p_raw = data['3p'][-1] if data['3p'] else calculate_display_rating(1500, 0)
            data['3p'].append(last_3p_raw)
        else:
            data['3p'].append(val_mode)
            last_4p_raw = data['4p'][-1] if data['4p'] else calculate_display_rating(1500, 0)
            data['4p'].append(last_4p_raw)

    return render_template('player.html', player=p, stats=stats, history=history, graph_data=data)
