# Cortex QRTOS — Developer Guide & Git Workflow

This guide covers local environment setup, testing, running the backend server, and the engineering contribution workflow.

---

## 1. Local Environment Setup

### Prerequisites
- Python 3.9+ installed
- Git
- SQLite 3 (built-in with Python)

### Setup Steps

```bash
# 1. Navigate to the server directory
cd server

# 2. Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt   # or ensure pytest, fastapi, uvicorn, sqlalchemy, pydantic are installed

# 4. Initialize environment configuration
cp .env.example .env
```

### Environment Variables (`.env`)
Ensure your `.env` contains local settings:
```ini
APP_ENV=development
HOST=127.0.0.1
PORT=8000
DATABASE_URL=sqlite:///cortex.db
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
STEP_KM=10.0
TIME_HORIZON_STEPS=10
SLOT_MINUTES=5
H_MIN=1
```

---

## 2. Seeding & Database Initialization

Seed the canonical Indian Railways 90 km corridor (Stations A, B, C; Segments S1, S2; Loop X1; Rajdhani & Goods trains):

```bash
# Run the database seeding script
venv/bin/python scripts/seed_mvp_world.py
```

---

## 3. Running Automated Tests

Always ensure the entire test suite passes before submitting code:

```bash
# Run all unit, integration, and contract tests (29 tests)
venv/bin/pytest -v

# Run only interval-tree conflict detection tests
venv/bin/pytest tests/unit/test_interval_tree.py -v

# Run TEG and Modified Dijkstra pathfinding tests
venv/bin/pytest tests/unit/test_pathfinder.py -v

# Run API visual contract tests
venv/bin/pytest tests/unit/test_visual_contracts.py -v
```

---

## 4. Running the Backend Server Locally

Use the dedicated launcher:

```bash
# Start server with live reload on http://127.0.0.1:8000
venv/bin/python run.py
```

- **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Redoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 5. Engineering Git & PR Workflow

> [!IMPORTANT]
> **Always take a branch cut and open a Pull Request (PR)**. Never commit directly to `main`.

Follow this standard Git workflow for all features, algorithm updates, or bug fixes:

### Step 1: Sync with Main
```bash
git checkout main
git pull origin main
```

### Step 2: Cut a New Feature Branch
Name branches with standard prefixes (`feat/`, `fix/`, `refactor/`, `docs/`, `test/`):
```bash
git checkout -b feat/interval-tree-scaling
# or
git checkout -b feat/cp-sat-formulation
```

### Step 3: Develop & Test
Make your changes, write tests in `tests/unit/` or `tests/integration/`, and verify:
```bash
venv/bin/pytest -v
```

### Step 4: Commit with Descriptive Messages
Use conventional commit prefixes:
```bash
git add src/ tests/ docs/
git commit -m "feat(conflict): implement AVL augmented interval tree for O(n log n) scaling"
```

### Step 5: Push Branch & Open a PR
```bash
git push -u origin feat/interval-tree-scaling
```

### Step 6: PR Review Checklist
Before requesting review on GitHub / GitLab, confirm:
- [ ] All automated tests pass (`venv/bin/pytest -v`).
- [ ] No regression in API contracts (`tests/unit/test_visual_contracts.py`).
- [ ] Database schema changes include auto-migration checks in `database.py`.
- [ ] Relevant documentation updated under `docs/`.
