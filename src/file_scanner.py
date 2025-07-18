import os
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from .utils import get_file_metadata
from .database_manager import DatabaseManager

class FileScanner:
    def __init__(self, db_manager: DatabaseManager, num_threads=None):
        self.db_manager = db_manager
        self.num_threads = num_threads if num_threads else os.cpu_count() * 2
        self.path_queue = Queue()
        self.total_files_scanned = 0
        self.total_directories_scanned = 0
        self.active_scan_tasks = 0

    def start_scanning(self, root_paths):
        """Initiates the multi-threaded file scanning process."""
        print(f"\nStarting file scan with {self.num_threads} threads...")
        
        for path in root_paths:
            self.path_queue.put(path)
            self.total_directories_scanned += 1
            self.active_scan_tasks += 1

        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            for _ in range(self.num_threads):
                executor.submit(self._scan_directory_task)
            
            self.path_queue.join() 
            
            for _ in range(self.num_threads):
                self.path_queue.put(None) 

            executor.shutdown(wait=True) 

        self.db_manager.set_indexing_finished()
        print(f"\nFile scanning completed. Scanned {self.total_files_scanned} files and {self.total_directories_scanned} directories.")

    def _scan_directory_task(self):
        """Worker task for scanning directories."""
        while True:
            current_dir = self.path_queue.get()
            
            if current_dir is None: 
                self.path_queue.task_done()
                break

            try:
                for entry in os.scandir(current_dir):
                    if entry.is_dir(follow_symlinks=False):
                        self.path_queue.put(entry.path)
                        self.active_scan_tasks += 1
                        self.total_directories_scanned += 1
                    elif entry.is_file(follow_symlinks=False):
                        metadata = get_file_metadata(entry.path)
                        if metadata:
                            self.db_manager.add_file_to_queue(metadata)
                            self.total_files_scanned += 1
            except PermissionError:
                pass
            except Exception as e:
                print(f"Error scanning {current_dir}: {e}")
            finally:
                self.path_queue.task_done()
                self.active_scan_tasks -= 1