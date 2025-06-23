import logging
import sqlite3
import os
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DataManager:
    """Manages file I/O for pipeline intermediates and outputs."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.temp_dir = Path(config["pipeline"]["temp_dir"])  # data/temp
        self.pdf_dir = Path(config["pipeline"]["pdf_dir"]).resolve()
        self.input_dir = Path(config["pipeline"]["output_dir"]) / "inputs"  # data/inputs
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)

    def save_temp(self, id: int, type: str, ext: str, content: str) -> str:
        """Save temporary file to data/temp/<id>_<type>.<ext>."""
        path = self.temp_dir / f"{id:03d}_{type}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug(f"Saved {type} to {path}")
        return str(path)

    def save_image(self, id: int, filename: str, content: bytes) -> str:
        """Save image to data/temp/<id>_images/<filename>."""
        path = self.temp_dir / f"{id:03d}_images" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        logger.debug(f"Saved image to {path}")
        return str(path)

    def save_pdf(self, id: int, input_type: str, content: bytes) -> str:
        """Save PDF to data/pdfs/<id>_<input_type>_notes.pdf."""
        path = self.pdf_dir / f"{id:03d}_{input_type}_notes.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        logger.info(f"Saved PDF to {path}")
        return str(path)

    def load_temp(self, id: int, type: str, ext: str) -> str:
        """Load content from data/temp/<id>_<type>.<ext>."""
        path = self.temp_dir / f"{id:03d}_{type}.{ext}"
        if not path.exists():
            logger.error(f"File {path} does not exist")
            raise FileNotFoundError(f"File {path} does not exist")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.debug(f"Loaded {type} from {path}")
        return content

    def clear_temp(self, id: int) -> None:
        """Delete files in data/temp/ for the given id."""
        temp_dir = self.temp_dir / f"{id:03d}_images"
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)
        for file in self.temp_dir.glob(f"{id:03d}_*"):
            file.unlink()
        logger.info(f"Cleared temp files for id {id:03d}")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

class StateManager:
    """Manages pipeline state in SQLite database."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._migrate_db()

    def _migrate_db(self) -> None:
        """Check and migrate tasks table schema."""
        try:
            self.cursor.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in self.cursor.fetchall()}
            required_columns = {"id", "input_data", "input_type", "step_name", "output_path", "status"}
            # Check if table exists and has the correct columns
            if not columns.issuperset(required_columns):
                logger.warning("Tasks table schema outdated or missing. Recreating table.")
                self.cursor.execute("DROP TABLE IF EXISTS tasks")
                self._init_db()
                return

            # Check if the CHECK constraint includes 'pending'
            self.cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
            create_table_sql = self.cursor.fetchone()[0]
            if "CHECK(status IN ('pending', 'success', 'failed'))" not in create_table_sql:
                logger.warning("Tasks table CHECK constraint outdated. Recreating table.")
                self.cursor.execute("DROP TABLE IF EXISTS tasks")
                self._init_db()
            else:
                logger.debug("Tasks table schema is up-to-date.")
        except sqlite3.OperationalError:
            logger.info("No tasks table found. Creating new table.")
            self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with tasks table for step outputs."""
        self.cursor.execute("""
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_data TEXT,
                input_type TEXT,
                step_name TEXT,
                output_path TEXT,
                status TEXT CHECK(status IN ('pending', 'success', 'failed')),
                UNIQUE (input_data, input_type, step_name)
            )
        """)
        self.conn.commit()
        logger.info(f"Initialized tasks table in {self.db_path}")

    def save_step_output(self, input_data: str, input_type: str, id: int, step_name: str, output_path: str) -> None:
        """Save step output to tasks.db."""
        self.cursor.execute("""
            INSERT OR REPLACE INTO tasks (input_data, input_type, id, step_name, output_path, status)
            VALUES (?, ?, ?, ?, ?, 'success')
        """, (input_data, input_type, id, step_name, output_path))
        self.conn.commit()
        logger.debug(f"Saved {step_name} output for {input_data} (id {id:03d}) to {output_path}")

    def get_step_output(self, input_data: str, input_type: str, id: int, step_name: str) -> Optional[str]:
        """Get cached output path for a step, if it exists and is valid."""
        self.cursor.execute("""
            SELECT output_path FROM tasks
            WHERE input_data = ? AND input_type = ? AND id = ? AND step_name = ? AND status = 'success'
        """, (input_data, input_type, id, step_name))
        result = self.cursor.fetchone()
        if result is None or result[0] is None:
            return None
        return result[0] if os.path.exists(result[0]) else None

    def save_success(self, input_data: str, input_type: str, id: int, pdf_path: str) -> None:
        """Save successful pipeline run (PDF) to tasks.db."""
        self.save_step_output(input_data, input_type, id, "PdfStep", pdf_path)
        # Update Init task status to 'success'
        self.cursor.execute("""
            UPDATE tasks SET status = 'success'
            WHERE input_data = ? AND input_type = ? AND step_name = 'Init'
        """, (input_data, input_type))
        self.conn.commit()
        logger.info(f"Saved successful pipeline state for {input_data} (id {id:03d})")

    def get_pdf_path(self, input_data: str, input_type: str, id: int) -> Optional[str]:
        """Get PDF path for a given input, if it exists."""
        self.cursor.execute("""
            SELECT output_path FROM tasks
            WHERE input_data = ? AND input_type = ? AND id = ? AND step_name = 'PdfStep' AND status = 'success'
        """, (input_data, input_type, id))
        result = self.cursor.fetchone()
        if result is None or result[0] is None:
            logger.debug(f"No valid PDF path found for {input_data} (id {id:03d})")
            return None
        if not os.path.exists(result[0]):
            logger.warning(f"PDF path {result[0]} does not exist for {input_data} (id {id:03d})")
            return None
        return result[0]

    def log_error(self, input_data: str, input_type: str, id: int, step_name: str, error: str) -> None:
        """Log error to data/outputs/errors.log and tasks.db."""
        log_path = self.db_path.parent / "errors.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{input_data} (id {id:03d}): {step_name} failed: {error}\n")
        logger.error(f"{input_data} (id {id:03d}): {step_name} failed: {error}")
        self.cursor.execute("""
            INSERT OR REPLACE INTO tasks (input_data, input_type, id, step_name, output_path, status)
            VALUES (?, ?, ?, ?, NULL, 'failed')
        """, (input_data, input_type, id, step_name))
        self.conn.commit()

    def get_index(self, input_data: str, input_type: str) -> int:
        """Get the next available id or reuse existing id for the input."""
        # Check if a task already exists for this input_data and input_type with step_name 'Init'
        self.cursor.execute("""
            SELECT id FROM tasks
            WHERE input_data = ? AND input_type = ? AND step_name = 'Init'
        """, (input_data, input_type))
        result = self.cursor.fetchone()
        
        if result:
            id = result[0]
            # Optionally reset status to 'pending' for retry
            self.cursor.execute("""
                UPDATE tasks SET status = 'pending'
                WHERE id = ? AND step_name = 'Init'
            """, (id,))
            self.conn.commit()
            logger.debug(f"Reusing existing ID {id} for {input_data}")
            return id
        
        # Insert new task if no existing task found
        self.cursor.execute("""
            INSERT INTO tasks (input_data, input_type, step_name, status)
            VALUES (?, ?, ?, 'pending')
        """, (input_data, input_type, "Init"))
        self.conn.commit()
        self.cursor.execute("SELECT last_insert_rowid()")
        id = self.cursor.fetchone()[0]
        logger.debug(f"Assigned new ID {id} for {input_data}")
        return id

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()