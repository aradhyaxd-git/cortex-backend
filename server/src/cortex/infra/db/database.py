# src/cortex/infra/db/database.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from cortex.config import DATABASE_URL

# Connect args: check_same_thread only applies to SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)

    # Auto-migrate SQLite schema for newly added columns if table already existed
    with engine.connect() as conn:
        # Check trains table columns
        res = conn.execute(text("PRAGMA table_info(trains)"))
        train_cols = {row[1] for row in res.fetchall()}
        if train_cols and "is_held" not in train_cols:
            conn.execute(text("ALTER TABLE trains ADD COLUMN is_held BOOLEAN DEFAULT 0 NOT NULL"))
            conn.commit()
        if train_cols and "delay_minutes" not in train_cols:
            conn.execute(text("ALTER TABLE trains ADD COLUMN delay_minutes FLOAT DEFAULT 0.0 NOT NULL"))
            conn.commit()

        # Check audit_logs table columns
        res_audit = conn.execute(text("PRAGMA table_info(audit_logs)"))
        audit_cols = {row[1] for row in res_audit.fetchall()}
        if audit_cols and "controller_id" not in audit_cols:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN controller_id VARCHAR DEFAULT 'dev_controller'"))
            conn.commit()