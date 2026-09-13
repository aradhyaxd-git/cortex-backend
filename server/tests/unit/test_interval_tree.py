# tests/unit/test_interval_tree.py
import pytest
from datetime import datetime, timedelta, timezone
from cortex.engine.conflict.detector import OccupationInterval, detect_conflict, detect_conflicts_batch
from cortex.engine.conflict.interval_tree import IntervalTree, CorridorIntervalIndex


@pytest.fixture
def base_time():
    return datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)


def test_empty_interval_tree_returns_no_overlaps(base_time):
    tree = IntervalTree()
    query = OccupationInterval(
        train_id="T1",
        segment_id="S1",
        entry_time=base_time,
        exit_time=base_time + timedelta(minutes=15),
        priority=1
    )
    assert len(tree) == 0
    assert tree.find_overlaps(query) == []
    assert tree.all_intervals() == []


def test_interval_tree_disjoint_and_overlapping_queries(base_time):
    tree = IntervalTree()

    # T1: 10:10 -> 10:25
    t1 = OccupationInterval(
        train_id="T1",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=10),
        exit_time=base_time + timedelta(minutes=25),
        priority=1
    )
    tree.insert(t1)

    # Disjoint before: 10:00 -> 10:05
    q_before = OccupationInterval(
        train_id="Q1",
        segment_id="S1",
        entry_time=base_time,
        exit_time=base_time + timedelta(minutes=5),
        priority=2
    )
    assert tree.find_overlaps(q_before) == []

    # Disjoint after: 10:30 -> 10:40
    q_after = OccupationInterval(
        train_id="Q2",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=30),
        exit_time=base_time + timedelta(minutes=40),
        priority=2
    )
    assert tree.find_overlaps(q_after) == []

    # Touching boundaries (no headway margin): 10:25 -> 10:35
    q_touch = OccupationInterval(
        train_id="Q3",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=25),
        exit_time=base_time + timedelta(minutes=35),
        priority=2
    )
    assert tree.find_overlaps(q_touch) == []

    # Partial overlap: 10:20 -> 10:35
    q_overlap = OccupationInterval(
        train_id="Q4",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=20),
        exit_time=base_time + timedelta(minutes=35),
        priority=2
    )
    overlaps = tree.find_overlaps(q_overlap)
    assert len(overlaps) == 1
    assert overlaps[0].train_id == "T1"


def test_interval_tree_headway_margin_enforcement(base_time):
    tree = IntervalTree()

    # Train A occupies 10:00 -> 10:15
    train_a = OccupationInterval(
        train_id="A",
        segment_id="S1",
        entry_time=base_time,
        exit_time=base_time + timedelta(minutes=15),
        priority=1
    )
    tree.insert(train_a)

    # Train B enters at 10:17 (2 min gap). Without headway, no overlap.
    train_b = OccupationInterval(
        train_id="B",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=17),
        exit_time=base_time + timedelta(minutes=30),
        priority=2
    )

    # Zero headway margin: no conflict
    assert tree.find_overlaps(train_b, headway_margin=timedelta(0)) == []

    # 3-minute safety headway margin H_min: flags near-miss conflict!
    conflicts_with_headway = tree.find_overlaps(train_b, headway_margin=timedelta(minutes=3))
    assert len(conflicts_with_headway) == 1
    assert conflicts_with_headway[0].train_id == "A"


def test_interval_tree_avl_balancing_and_multiple_overlaps(base_time):
    tree = IntervalTree()

    # Insert 10 sequential intervals (tests AVL rotations and height balance)
    intervals = []
    for i in range(10):
        inv = OccupationInterval(
            train_id=f"T_{i}",
            segment_id="S1",
            entry_time=base_time + timedelta(minutes=i * 10),
            exit_time=base_time + timedelta(minutes=i * 10 + 15),
            priority=1
        )
        intervals.append(inv)
        tree.insert(inv)

    assert len(tree) == 10
    # AVL tree with 10 nodes must have height <= 4
    assert tree.root.height <= 4

    # Query spanning across T_2, T_3, T_4 (minutes 25 -> 42)
    query = OccupationInterval(
        train_id="QuerySpan",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=25),
        exit_time=base_time + timedelta(minutes=42),
        priority=1
    )
    overlaps = tree.find_overlaps(query)
    overlapping_ids = {inv.train_id for inv in overlaps}
    # T_2: 20->35 (overlaps 25->42)
    # T_3: 30->45 (overlaps 25->42)
    # T_4: 40->55 (overlaps 25->42)
    assert overlapping_ids == {"T_2", "T_3", "T_4"}


def test_corridor_interval_index_multi_segment_isolation(base_time):
    index = CorridorIntervalIndex()

    # Train A on S1, Train B on S2 with EXACTLY identical time windows
    inv_a = OccupationInterval(
        train_id="Train_A",
        segment_id="S1",
        entry_time=base_time,
        exit_time=base_time + timedelta(minutes=20),
        priority=1
    )
    inv_b = OccupationInterval(
        train_id="Train_B",
        segment_id="S2",
        entry_time=base_time,
        exit_time=base_time + timedelta(minutes=20),
        priority=2
    )

    index.add_reservation(inv_a)
    index.add_reservation(inv_b)

    # Different segments must never conflict
    assert index.find_all_conflicts() == []
    assert index.find_conflicts_for_interval(inv_a) == []
    assert index.find_conflicts_for_interval(inv_b) == []

    # Add Train C on S1 overlapping with Train A
    inv_c = OccupationInterval(
        train_id="Train_C",
        segment_id="S1",
        entry_time=base_time + timedelta(minutes=10),
        exit_time=base_time + timedelta(minutes=25),
        priority=3
    )
    index.add_reservation(inv_c)

    conflicts = index.find_all_conflicts()
    assert len(conflicts) == 1
    pair_trains = {conflicts[0][0].train_id, conflicts[0][1].train_id}
    assert pair_trains == {"Train_A", "Train_C"}


def test_equivalence_with_pairwise_detector(base_time):
    """
    Stress test verifying that CorridorIntervalIndex matches brute-force O(n^2)
    pairwise detection on a synthetic corridor schedule of 24 train intervals.
    """
    import random
    rng = random.Random(42)

    segments = ["S1", "S2", "S3"]
    synthetic_intervals = []

    for i in range(24):
        seg = segments[rng.randint(0, len(segments) - 1)]
        start_min = rng.randint(0, 120)
        duration_min = rng.randint(10, 30)
        inv = OccupationInterval(
            train_id=f"Train_{i:02d}",
            segment_id=seg,
            entry_time=base_time + timedelta(minutes=start_min),
            exit_time=base_time + timedelta(minutes=start_min + duration_min),
            priority=rng.randint(1, 3)
        )
        synthetic_intervals.append(inv)

    # 1. Ground truth via naive O(n^2) pairwise check
    ground_truth_pairs = set()
    for i in range(len(synthetic_intervals)):
        for j in range(i + 1, len(synthetic_intervals)):
            a = synthetic_intervals[i]
            b = synthetic_intervals[j]
            if detect_conflict(a, b):
                pair = tuple(sorted([a.train_id, b.train_id]))
                ground_truth_pairs.add(pair)

    # 2. Output via CorridorIntervalIndex / detect_conflicts_batch
    index_conflicts = detect_conflicts_batch(synthetic_intervals)
    index_pairs = {tuple(sorted([a.train_id, b.train_id])) for a, b in index_conflicts}

    # Assert exact mathematical equivalence
    assert index_pairs == ground_truth_pairs
    assert len(index_pairs) > 0  # Confirms non-trivial number of conflicts found
