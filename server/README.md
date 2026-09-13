# Cortex QRTOS — Backend Engine

FastAPI and mathematical algorithms for the Cortex Quasi-Real-Time Operating System.

## Architecture

- **Engine (`src/cortex/engine/`)**:
  - `conflict/interval_tree.py`: AVL Augmented Interval Tree for $O(\log n + k)$ conflict search.
  - `conflict/detector.py`: Pairwise and batch overlap checking with headway buffer ($H_{\min}$).
  - `decision/greedy.py`: Priority tie-breaking and resolution.
  - `teg/builder.py`: Time-Expanded Graph constructor.
  - `teg/pathfinder.py`: Modified Dijkstra relaxation solver.
- **Application (`src/cortex/application/`)**: Service orchestration (`SimulationService`, `ConflictService`, `OverrideService`, `AnalyticsService`).
- **Domain (`src/cortex/domain/`)**: Canonical models, state machine transitions, and enums.
- **Infrastructure (`src/cortex/infra/db/`)**: SQLite database engine with auto-migration and repositories.
- **API (`src/cortex/api/routes/`)**: REST routes and WebSocket telemetry endpoints.

---

## Quickstart

```bash
# 1. Setup virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Seed database
python scripts/seed_mvp_world.py

# 3. Run all tests
venv/bin/pytest -v

# 4. Run server locally
python run.py
```

Access Swagger UI at `http://127.0.0.1:8000/docs`.

For in-depth mathematical proofs and API schemas, see [`../docs/`](../docs/).
