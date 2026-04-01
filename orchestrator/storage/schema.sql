CREATE TABLE IF NOT EXISTS sessions (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    task_name TEXT UNIQUE NOT NULL,
    branch TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    claude_session_id TEXT,
    created_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    total_cost_usd REAL DEFAULT 0.0,
    max_budget_usd REAL DEFAULT 5.0,
    error_count INTEGER DEFAULT 0
);
