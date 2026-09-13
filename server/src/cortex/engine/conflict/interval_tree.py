# src/cortex/engine/conflict/interval_tree.py
"""
Augmented Interval Tree and Spatial-Temporal Corridor Index for Railway Conflict Detection.

Provides O(n log n) index construction and O(log n + k) overlap queries per segment,
supporting safety headway margins (H_min) and dynamic multi-segment corridor partitioning.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
from cortex.engine.conflict.detector import OccupationInterval


@dataclass
class IntervalNode:
    """
    Node in an augmented AVL Interval Tree.
    Stores the interval's [low, high) bounds and maintains `max_high`
    representing the maximum `high` value across its entire subtree.
    """
    low: datetime
    high: datetime
    max_high: datetime
    height: int = 1
    intervals: List[OccupationInterval] = field(default_factory=list)
    left: Optional["IntervalNode"] = None
    right: Optional["IntervalNode"] = None


class IntervalTree:
    """
    Self-balancing AVL Augmented Interval Tree.
    Maintains max_high to guarantee O(log n + k) search time for intervals overlapping [q_low, q_high).
    """
    def __init__(self):
        self.root: Optional[IntervalNode] = None
        self._count: int = 0

    def __len__(self) -> int:
        return self._count

    def clear(self) -> None:
        self.root = None
        self._count = 0

    @staticmethod
    def _height(node: Optional[IntervalNode]) -> int:
        return node.height if node else 0

    @staticmethod
    def _get_balance(node: Optional[IntervalNode]) -> int:
        return (IntervalTree._height(node.left) - IntervalTree._height(node.right)) if node else 0

    @staticmethod
    def _update_node(node: IntervalNode) -> None:
        node.height = 1 + max(IntervalTree._height(node.left), IntervalTree._height(node.right))
        m = node.high
        if node.left and node.left.max_high > m:
            m = node.left.max_high
        if node.right and node.right.max_high > m:
            m = node.right.max_high
        node.max_high = m

    @staticmethod
    def _rotate_right(y: IntervalNode) -> IntervalNode:
        x = y.left
        assert x is not None
        t = x.right
        x.right = y
        y.left = t
        IntervalTree._update_node(y)
        IntervalTree._update_node(x)
        return x

    @staticmethod
    def _rotate_left(x: IntervalNode) -> IntervalNode:
        y = x.right
        assert y is not None
        t = y.left
        y.left = x
        x.right = t
        IntervalTree._update_node(x)
        IntervalTree._update_node(y)
        return y

    def insert(self, interval: OccupationInterval) -> None:
        """
        Inserts an occupation interval into the balanced augmented tree.
        Runs in O(log n) time.
        """
        self.root = self._insert_rec(self.root, interval)
        self._count += 1

    def _insert_rec(self, node: Optional[IntervalNode], interval: OccupationInterval) -> IntervalNode:
        if node is None:
            return IntervalNode(
                low=interval.entry_time,
                high=interval.exit_time,
                max_high=interval.exit_time,
                height=1,
                intervals=[interval]
            )

        key = (interval.entry_time, interval.exit_time)
        node_key = (node.low, node.high)

        if key == node_key:
            # Exact boundary match: attach to node bucket
            node.intervals.append(interval)
            return node
        elif key < node_key:
            node.left = self._insert_rec(node.left, interval)
        else:
            node.right = self._insert_rec(node.right, interval)

        IntervalTree._update_node(node)

        # AVL Balancing
        balance = self._get_balance(node)

        # Left Left
        if balance > 1 and node.left and key < (node.left.low, node.left.high):
            return self._rotate_right(node)

        # Right Right
        if balance < -1 and node.right and key > (node.right.low, node.right.high):
            return self._rotate_left(node)

        # Left Right
        if balance > 1 and node.left and key > (node.left.low, node.left.high):
            node.left = self._rotate_left(node.left)
            return self._rotate_right(node)

        # Right Left
        if balance < -1 and node.right and key < (node.right.low, node.right.high):
            node.right = self._rotate_right(node.right)
            return self._rotate_left(node)

        return node

    def find_overlaps(
        self,
        query: OccupationInterval,
        headway_margin: timedelta = timedelta(0),
        exclude_train_id: Optional[str] = None
    ) -> List[OccupationInterval]:
        """
        Finds all intervals in this tree overlapping [query.entry_time - headway_margin, query.exit_time + headway_margin).
        Runs in O(log n + k) time where k is the number of reported conflicts.
        """
        q_low = query.entry_time - headway_margin
        q_high = query.exit_time + headway_margin
        results: List[OccupationInterval] = []
        self._find_overlaps_rec(self.root, q_low, q_high, results, exclude_train_id)
        return results

    def _find_overlaps_rec(
        self,
        node: Optional[IntervalNode],
        q_low: datetime,
        q_high: datetime,
        results: List[OccupationInterval],
        exclude_train_id: Optional[str]
    ) -> None:
        if node is None:
            return

        # Prune left subtree if left child's max_high <= q_low
        if node.left is not None and node.left.max_high > q_low:
            self._find_overlaps_rec(node.left, q_low, q_high, results, exclude_train_id)

        # Check overlap with current node: [node.low, node.high) overlaps [q_low, q_high)
        # iff node.low < q_high and q_low < node.high
        if node.low < q_high and q_low < node.high:
            for item in node.intervals:
                if exclude_train_id is None or item.train_id != exclude_train_id:
                    results.append(item)

        # Prune right subtree if node.low >= q_high
        # Since tree is ordered by low, all nodes in right subtree have low >= node.low >= q_high
        if node.low < q_high:
            self._find_overlaps_rec(node.right, q_low, q_high, results, exclude_train_id)

    def all_intervals(self) -> List[OccupationInterval]:
        """Returns all intervals in in-order traversal."""
        out: List[OccupationInterval] = []
        self._inorder(self.root, out)
        return out

    def _inorder(self, node: Optional[IntervalNode], out: List[OccupationInterval]) -> None:
        if node:
            self._inorder(node.left, out)
            out.extend(node.intervals)
            self._inorder(node.right, out)


class CorridorIntervalIndex:
    """
    Multi-segment spatial-temporal corridor index.
    Segments act as discrete spatial resource partitions. Each segment possesses
    its own IntervalTree of temporal reservations.
    """
    def __init__(self):
        self._trees: Dict[str, IntervalTree] = {}

    def get_tree(self, segment_id: str) -> IntervalTree:
        if segment_id not in self._trees:
            self._trees[segment_id] = IntervalTree()
        return self._trees[segment_id]

    def add_reservation(self, interval: OccupationInterval) -> None:
        """Adds a train occupancy reservation for the interval's segment."""
        self.get_tree(interval.segment_id).insert(interval)

    def find_conflicts_for_interval(
        self,
        interval: OccupationInterval,
        headway_margin: timedelta = timedelta(0),
        exclude_same_train: bool = True
    ) -> List[OccupationInterval]:
        """
        Finds all conflicting train reservations on the target segment.
        """
        tree = self.get_tree(interval.segment_id)
        return tree.find_overlaps(
            query=interval,
            headway_margin=headway_margin,
            exclude_train_id=interval.train_id if exclude_same_train else None
        )

    def find_all_conflicts(
        self,
        headway_margin: timedelta = timedelta(0)
    ) -> List[Tuple[OccupationInterval, OccupationInterval]]:
        """
        Finds all unique pairwise conflicts across all corridor segments.
        Returns unique pairs (train_a_interval, train_b_interval).
        """
        conflicts: List[Tuple[OccupationInterval, OccupationInterval]] = []
        seen_pairs = set()

        for segment_id, tree in self._trees.items():
            intervals = tree.all_intervals()
            for interval in intervals:
                overlapping = tree.find_overlaps(
                    query=interval,
                    headway_margin=headway_margin,
                    exclude_train_id=interval.train_id
                )
                for other in overlapping:
                    pair_key = tuple(sorted([interval.train_id, other.train_id]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        conflicts.append((interval, other))

        return conflicts