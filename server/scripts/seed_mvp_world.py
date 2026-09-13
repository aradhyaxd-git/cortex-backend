# scripts/seed_mvp_world.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from cortex.config import get_mvp_world

def create_mvp_world() -> dict:
    """
    Instantiates the canonical MVP world from cortex.config:
    - 3 Stations (A, B, C)
    - 2 Segments (S1: A->B, S2: B->C)
    - 1 Crossing Loop (X1 at B, 750m)
    - 2 Trains (12951 Rajdhani, G1 Freight)
    """
    return get_mvp_world()

if __name__ == "__main__":
    world = create_mvp_world()
    print(f"Seeded MVP World: {len(world['stations'])} stations, {len(world['trains'])} trains.")