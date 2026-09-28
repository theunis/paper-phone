from __future__ import annotations

from paper_phone.modules.extras import _count_solutions, sudoku_puzzle


def test_sudoku_has_one_solution() -> None:
    puzzle, solution = sudoku_puzzle(seed=2026, clues=32)
    assert sum(v != 0 for row in puzzle for v in row) >= 32
    assert _count_solutions([row[:] for row in puzzle]) == 1
    for r in range(9):
        for c in range(9):
            if puzzle[r][c]:
                assert puzzle[r][c] == solution[r][c]
    for i in range(9):
        assert sorted(solution[i]) == list(range(1, 10))
        assert sorted(row[i] for row in solution) == list(range(1, 10))
