import mysql.connector
from mysql.connector import Error
from collections import deque
import threading
import time
from tqdm import tqdm 

class DatabaseManager:
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection = None # This will primarily be used by the main thread (e.g., for create_table)
        self.file_data_queue = deque() # Use deque for efficient append/pop from ends
        self.is_indexing_finished = False
        self.writer_thread = None
        self.stop_event = threading.Event() # To signal the writer thread to stop
        self.processed_count = 0 # Track files processed by writer
        self.tqdm_instance = None # To update progress bar from writer

    def connect(self):
        """Establishes a connection to the MySQL database for the current thread."""
        try:
            # Create a new connection instance
            new_connection = mysql.connector.connect(**self.db_config)
            if new_connection.is_connected():
                # Only print connection message if it's the initial connection from main thread
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
        """Closes the database connection (only if it's the main thread's connection).
           Other connections are closed by their respective threads."""
        if self.connection and self.connection.is_connected() and threading.current_thread() == threading.main_thread():
            self.connection.close()
            print("MySQL connection closed.")

    def create_table(self):
        """Creates the 'files' table if it doesn't exist."""
        # Ensure the main thread has a connection
        if not self.connection or not self.connection.is_connected():
            self.connection = self.connect()
            if not self.connection:
                print("Cannot create table: Main thread failed to connect to database.")
                return False # Indicate failure

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        filepath VARCHAR(4096) NOT NULL, -- NO UNIQUE HERE
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
            
            # DDL statements (like CREATE TABLE) implicitly commit in MySQL,
            # so an explicit commit here is not needed and can cause "commands out of sync".
            print("Table 'files' ensured to exist.")
            return True # Indicate success
        except Error as e:
            print(f"Error creating table: {e}")
            raise # Re-raise to stop execution if table can't be created

    # --- START ADDED CODE ---
    def clear_all_indexes(self):
        """Clears all data from the 'files' table."""
        # Ensure the main thread has a connection
        if not self.connection or not self.connection.is_connected():
            self.connection = self.connect()
            if not self.connection:
                print("Cannot clear indexes: Main thread failed to connect to database.")
                return False # Indicate failure

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE files;")
            # TRUNCATE TABLE is a DDL statement and implicitly commits.
            print("All previous indexes cleared from the database.")
            return True # Indicate success
        except Error as e:
            print(f"Error clearing indexes: {e}")
            # Do not re-raise if you want the app to handle gracefully,
            # but raise if you want it to fail hard on DB error.
            raise # Re-raise to indicate failure
    # --- END ADDED CODE ---

    def add_file_to_queue(self, file_metadata):
        """Adds file metadata to an in-memory queue."""
        self.file_data_queue.append(file_metadata)

    def set_indexing_finished(self):
        """Signals that all file scanning is complete."""
        self.is_indexing_finished = True

    def start_writer_thread(self, total_expected_files=0):
        """Starts a dedicated thread for writing data to the database."""
        self.tqdm_instance = tqdm(total=total_expected_files, unit="files", desc="Indexing progress")
        self.writer_thread = threading.Thread(target=self._database_writer_loop)
        self.writer_thread.start()

    def wait_for_writer_thread(self):
        """Waits for the database writer thread to complete."""
        if self.writer_thread:
            self.writer_thread.join()
        if self.tqdm_instance:
            self.tqdm_instance.close()

    def _database_writer_loop(self):
        """The main loop for the database writer thread."""
        writer_connection = None
        try:
            # Establish a NEW, dedicated connection for this thread
            writer_connection = self.connect()
            if not writer_connection or not writer_connection.is_connected():
                print("Database writer failed to establish its own connection, exiting.")
                return

            writer_connection.autocommit = False # Ensure transactions are used for batching
            cursor = writer_connection.cursor()
            batch_size = 1000 # Number of records to insert in one transaction
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

            while True: # Loop indefinitely until explicitly broken
                try:
                    # Use a small timeout to avoid busy-waiting, but let it block mostly
                    file_metadata = self.file_data_queue.popleft()
                    batch_data.append(file_metadata)

                    if len(batch_data) >= batch_size:
                        self._execute_batch(cursor, insert_sql, batch_data, writer_connection) # Pass writer_connection
                        batch_data.clear()
                except IndexError: # Queue is empty
                    # Check if indexing is finished AND queue is truly empty.
                    # If so, process any remaining batch_data and exit.
                    if self.is_indexing_finished and not self.file_data_queue:
                        break
                    time.sleep(0.01) # Small sleep if queue is empty, to prevent busy-waiting

            # Process any remaining data in the batch after loop breaks
            if batch_data:
                self._execute_batch(cursor, insert_sql, batch_data, writer_connection)
            
            cursor.close()
            # writer_connection.commit() # A final commit might be needed if there's any uncommitted data after the last batch
            print("\nDatabase writer thread finished.")

        except Error as e:
            print(f"Error in database writer thread: {e}")
        finally:
            if writer_connection and writer_connection.is_connected():
                writer_connection.close()


    def _execute_batch(self, cursor, sql, batch, connection_for_commit): # Add connection_for_commit parameter
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
            connection_for_commit.commit() # Use the passed connection for commit
            self.processed_count += len(batch)
            if self.tqdm_instance:
                self.tqdm_instance.update(len(batch))
        except Error as e:
            print(f"Error during batch execution: {e}")
            connection_for_commit.rollback()

    def stop_writer_thread(self):
        """Gracefully stops the writer thread."""
        self.stop_event.set()
        self.wait_for_writer_thread()