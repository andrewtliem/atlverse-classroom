from collections import defaultdict
from typing import Dict, Tuple

from models import SelfEvaluation, Material, Enrollment

AWARD_STAR_VALUES = {
    'gold': 3,
    'silver': 2,
    'bronze': 1
}


def calculate_awards_for_student(classroom_id: int, student_id: int) -> Dict[int, dict]:
    """Return award info by material for a student in a classroom."""
    evaluations = (
        SelfEvaluation.query
        .filter_by(classroom_id=classroom_id, student_id=student_id, is_ai_generated=True)
        .filter(SelfEvaluation.completed_at.isnot(None))
        .order_by(SelfEvaluation.created_at)
        .all()
    )

    evals_by_material = defaultdict(list)
    for e in evaluations:
        material_id = e.material_id if e.material_id else 0
        evals_by_material[material_id].append(e)

    awards = {}
    for material_id, evals in evals_by_material.items():
        best_passing_eval = None
        # Find the first evaluation with a score >= 80%
        for idx, ev in enumerate(evals):
            if ev.score is not None and ev.score >= 80:
                best_passing_eval = ev
                break # Found the first passing attempt

        if best_passing_eval:
            # Now find the attempt number for this specific evaluation
            attempt_num = evals.index(best_passing_eval) + 1 # 1-based index

            if attempt_num == 1:
                award = 'gold'
            elif attempt_num in [2, 3]:
                award = 'silver'
            else:
                award = 'bronze'
            material_title = "All Materials"
            if material_id != 0:
                material = Material.query.get(material_id)
                if material:
                    material_title = material.title
            awards[material_id] = {
                'award': award,
                'score': best_passing_eval.score, # Use the score from the best passing eval
                'attempts': attempt_num,
                'material_title': material_title,
            }
    return awards


def calculate_star_total(awards: Dict[int, dict]) -> int:
    """Calculate total stars from award mapping."""
    total = 0
    for info in awards.values():
        total += AWARD_STAR_VALUES.get(info.get('award'), 0)
    return total


def get_classroom_star_rankings(classroom_id: int) -> Tuple[Dict[int, dict], int]:
    """Return star totals and ranks for all students in a classroom."""
    enrollments = Enrollment.query.filter_by(classroom_id=classroom_id).all()
    star_list = []
    for enrollment in enrollments:
        awards = calculate_awards_for_student(classroom_id, enrollment.student_id)
        total = calculate_star_total(awards)
        star_list.append((enrollment.student_id, total))

    star_list.sort(key=lambda x: x[1], reverse=True)
    rankings = {}
    last_total = None
    rank = 0
    for i, (student_id, total) in enumerate(star_list, start=1):
        if total != last_total:
            rank = i
            last_total = total
        rankings[student_id] = {'star_total': total, 'rank': rank}
    return rankings, len(star_list)

