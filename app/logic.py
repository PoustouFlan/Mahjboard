# app/logic.py

# Configuration
UMA_4P = [20, 10, -10, -20]
UMA_3P = [20, 0, -20]

RATING_K = 1
RATING_DIV = 40.0
REDUCTION_RATE = 0.20

def calculate_signed_scores(raw_points):
    """
    Handles math for both 3P and 4P games.
    """
    game_type = len(raw_points) # 3 = sanma, 4 = normal
    target = sum(raw_points) // len(raw_points)
    uma = UMA_4P if game_type == 4 else UMA_3P

    indexed = [{'idx': i, 'raw': p} for i, p in enumerate(raw_points)]
    ranked = sorted(indexed, key=lambda x: x['raw'], reverse=True)

    # UMA egalites - on fait la moyenne sur ceux qui ont le même score
    uma = uma.copy()
    i = 0
    j = 1
    while i < game_type:
        # invariant: la plage ranked[i:j] a le même score
        while j < game_type and ranked[i]['raw'] == ranked[j]['raw']:
            j += 1
        if j - i > 1: # égalité de j-i joueurs
            true_uma = sum(uma[i:j]) / (j-i)
            for k in range(i, j):
                uma[k] = true_uma

        i = j
        j += 1

    final_scores = [0.0] * game_type
    applied_umas = [0.0] * game_type

    # Score + Uma
    for rank_idx, data in enumerate(ranked):
        s = (data['raw'] - target) / 1000.0 + uma[rank_idx]
        final_scores[data['idx']] = s
        applied_umas[data['idx']] = uma[rank_idx]

    return final_scores, uma

def calculate_rating_updates(current_ratings, signed_scores):
    """
    Generic algorithm (Works for General, 3P, and 4P lists).
    """
    table_avg = sum(current_ratings) / len(current_ratings)
    results = []

    for r_old, score in zip(current_ratings, signed_scores):
        correction = (table_avg - r_old) / RATING_DIV
        change = RATING_K * (score + correction)
        results.append({
            'new': round(r_old + change, 2),
            'change': change
        })

    return results


def calculate_display_rating(real_rating, games_played):
    """
    Applies the 'Newcomer Malus'.
    Display Rating = Real Rating - (1500 * 0.80^N)
    """
    if games_played < 0: return 0

    malus = 1500.0 * ((1 - REDUCTION_RATE) ** games_played)

    return real_rating - malus
