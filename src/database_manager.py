import mysql.connector
from mysql.connector import Error
from collections import deque
import threading
import time

class DatabaseManager:
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection = None
        self.file_data_queue = deque()
        self.is_indexing_finished = False
        self.writer_thread = None
        self.stop_event = threading.Event()
        self.processed_count = 0

    def connect(self):
        """Establishes a connection to the MySQL database for the current thread."""
        try:
            new_connection = mysql.connector.connect(**self.db_config)
            if new_connection.is_connected():
                if threading.current_thread() == threading.main_thread():
                    print(f"Connected to MySQL database: {self.db_config['database']}")
                return new_connection
        except Error as e:
            if threading.current_thread() == threading.main_thread():
                print(f"Error connecting to MySQL database: {e}")
            else:
                print(f"Error connecting to MySQL database in thread {threading.current_thread().name}: {e}")
            return None

    def close(self):
        """Closes the database connection (only if it's the main thread's connection)."""
        if self.connection and self.connection.is_connected() and threading.current_thread() == threading.main_thread():
            self.connection.close()
            print("MySQL connection closed.")

    def create_table(self):
        """Creates the 'files' table if it doesn't exist."""
        if not self.connection or not self.connection.is_connected():
            self.connection = self.connect()
            if not self.connection:
                print("Cannot create table: Main thread failed to connect to database.")
                return False

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        filepath VARCHAR(4096) NOT NULL,
                        filename VARCHAR(512) NOT NULL,
                        extension VARCHAR(50),
                        size BIGINT,
                        creation_time BIGINT,
                        modification_time BIGINT,
                        tags TEXT,
                        filepath_hash BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(filepath, 256))) STORED UNIQUE,
                        INDEX idx_filename (filename),
                        INDEX idx_filepath_prefix (filepath(191))
                    ) CHARACTER SET utf8;
                """)
            print("Table 'files' ensured to exist.")
            return True
        except Error as e:
            print(f"Error creating table: {e}")
            raise

    def clear_all_indexes(self):
        """Clears all data from the 'files' table."""
        if not self.connection or not self.connection.is_connected():
            self.connection = self.connect()
            if not self.connection:
                print("Cannot clear indexes: Main thread failed to connect to database.")
                return False

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE files;")
            print("All previous indexes cleared from the database.")
            return True
        except Error as e:
            print(f"Error clearing indexes: {e}")
            raise

    def add_file_to_queue(self, file_metadata):
        """Adds file metadata to an in-memory queue."""
        self.file_data_queue.append(file_metadata)

    def set_indexing_finished(self):
        """Signals that all file scanning is complete."""
        self.is_indexing_finished = True

    def start_writer_thread(self, total_expected_files=0):
        """Starts a dedicated thread for writing data to the database."""
        self.writer_thread = threading.Thread(target=self._database_writer_loop)
        self.writer_thread.start()

    def wait_for_writer_thread(self):
        """Waits for the database writer thread to complete."""
        if self.writer_thread:
            self.writer_thread.join()

    def _database_writer_loop(self):
        """The main loop for the database writer thread."""
        writer_connection = None
        try:
            writer_connection = self.connect()
            if not writer_connection or not writer_connection.is_connected():
                print("Database writer failed to establish its own connection, exiting.")
                return

            writer_connection.autocommit = False
            cursor = writer_connection.cursor()
            batch_size = 1000
            batch_data = []

            insert_sql = """
                INSERT INTO files (filepath, filename, extension, size, creation_time, modification_time, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    filename = VALUES(filename),
                    extension = VALUES(extension),
                    size = VALUES(size),
                    creation_time = VALUES(creation_time),
                    modification_time = VALUES(modification_time),
                    tags = VALUES(tags)
            """

            while True:
                try:
                    file_metadata = self.file_data_queue.popleft()
                    batch_data.append(file_metadata)

                    if len(batch_data) >= batch_size:
                        self._execute_batch(cursor, insert_sql, batch_data, writer_connection)
                        batch_data.clear()
                except IndexError: # Queue is empty
                    if self.is_indexing_finished and not self.file_data_queue:
                        break
                    time.sleep(0.01)

            if batch_data:
                self._execute_batch(cursor, insert_sql, batch_data, writer_connection)
            
            cursor.close()
            print("\nDatabase writer thread finished.")

        except Error as e:
            print(f"Error in database writer thread: {e}")
        finally:
            if writer_connection and writer_connection.is_connected():
                writer_connection.close()

    def _execute_batch(self, cursor, sql, batch, connection_for_commit):
        """Executes a batch of inserts/updates."""
        data_tuples = []
        for meta in batch:
            data_tuples.append((
                meta['filepath'], meta['filename'], meta['extension'],
                meta['size'], meta['creation_time'], meta['modification_time'],
                meta['tags']
            ))
        try:
            cursor.executemany(sql, data_tuples)
            connection_for_commit.commit()
            self.processed_count += len(batch)
        except Error as e:
            print(f"Error during batch execution: {e}")
            connection_for_commit.rollback()

    def stop_writer_thread(self):
        """Gracefully stops the writer thread."""
        self.stop_event.set()
        self.wait_for_writer_thread()