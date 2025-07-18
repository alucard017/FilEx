import os
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from tqdm import tqdm
import time

from .utils import get_file_metadata
from .database_manager import DatabaseManager

class FileScanner:
    def __init__(self, db_manager: DatabaseManager, num_threads=None):
        self.db_manager = db_manager
        self.num_threads = num_threads if num_threads else os.cpu_count() * 2
        self.path_queue = Queue() # Queue of directories to scan
        self.total_files_scanned = 0
        self.total_directories_scanned = 0
        self.active_scan_tasks = 0 # To track how many directories are still being scanned or queued

    def start_scanning(self, root_paths):
        """
        Initiates the multi-threaded file scanning process.
        """
        print(f"\nStarting file scan with {self.num_threads} threads...")
        
        # Add initial root paths to the queue and update active_scan_tasks
        for path in root_paths:
            self.path_queue.put(path)
            self.total_directories_scanned += 1 # Count root paths as directories scanned
            self.active_scan_tasks += 1 # Increment for each root path initially put

        # Use a lock to protect total_files_scanned and total_directories_scanned updates if needed (for more complex scenarios)
        # self.lock = threading.Lock() 

        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            # Submit worker tasks
            for _ in range(self.num_threads):
                executor.submit(self._scan_directory_task)

            # Wait for all directories in the queue to be processed
            # path_queue.join() will block until all items put() into the queue have been task_done().
            self.path_queue.join() 
            
            # Now that all processing of directories is complete, signal workers to exit
            # Put 'None' sentinels for each worker thread to ensure they all shut down gracefully.
            for _ in range(self.num_threads):
                self.path_queue.put(None) 

            # Shut down the executor and wait for all threads to terminate
            executor.shutdown(wait=True) 

        self.db_manager.set_indexing_finished() # Signal DB writer that no more data is coming
        print(f"\nFile scanning completed. Scanned {self.total_files_scanned} files and {self.total_directories_scanned} directories.")

    def _scan_directory_task(self):
        """
        Worker task for scanning directories.
        Puts new directories back into the queue for other workers.
        """
        while True:
            current_dir = self.path_queue.get() # Blocks until an item is available
            
            if current_dir is None: # Check for sentinel value to stop the worker
                self.path_queue.task_done()
                break # Exit the thread's loop

            try:
                # print(f"Thread {threading.current_thread().name} scanning: {current_dir}") # Debug print

                for entry in os.scandir(current_dir):
                    if entry.is_dir(follow_symlinks=False):
                        self.path_queue.put(entry.path)
                        # --- CRITICAL CHANGE: Increment active_scan_tasks for new directories ---
                        # This ensures Queue.join() knows there's more work in the chain.
                        self.active_scan_tasks += 1 
                        self.total_directories_scanned += 1
                    elif entry.is_file(follow_symlinks=False):
                        metadata = get_file_metadata(entry.path)
                        if metadata:
                            self.db_manager.add_file_to_queue(metadata)
                            self.total_files_scanned += 1
                            # print(f"DEBUG: Thread {threading.current_thread().name} added file: {entry.path}") # Debug print
            except PermissionError:
                # print(f"Permission denied to access: {current_dir}") # Uncomment for debugging
                pass # Silently ignore directories we can't access
            except Exception as e:
                print(f"Error scanning {current_dir}: {e}")
            finally:
                self.path_queue.task_done() # Mark this specific directory task as done
                # --- CRITICAL CHANGE: Decrement active_scan_tasks when a directory is processed ---
                self.active_scan_tasks -= 1
        
        # print(f"Thread {threading.current_thread().name} finished scanning loop.") # Debug print