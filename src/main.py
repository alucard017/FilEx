import os
import time
import sys

from .utils import parse_db_config
from .database_manager import DatabaseManager
from .file_scanner import FileScanner
from .search_manager import SearchManager

# Ensure the parent directory is in the sys.path for module imports
# This is crucial when running from the project root using 'python -m src.main'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def get_indexed_roots():
    """Reads previously indexed root paths from a file."""
    indexed_roots_file = os.path.join(project_root, 'data', 'indexed_roots.txt')
    if not os.path.exists(indexed_roots_file):
        return []
    with open(indexed_roots_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_indexed_roots(roots):
    """Saves newly indexed root paths to a file."""
    indexed_roots_file = os.path.join(project_root, 'data', 'indexed_roots.txt')
    os.makedirs(os.path.dirname(indexed_roots_file), exist_ok=True)
    with open(indexed_roots_file, 'w', encoding='utf-8') as f:
        for root in roots:
            f.write(root + '\n')

def clear_indexed_roots_file():
    """Removes the indexed_roots.txt file if it exists."""
    indexed_roots_file = os.path.join(project_root, 'data', 'indexed_roots.txt')
    if os.path.exists(indexed_roots_file):
        try:
            os.remove(indexed_roots_file)
            print("Indexed roots file cleared.")
        except OSError as e:
            print(f"Error clearing indexed roots file: {e}")
    else:
        print("Indexed roots file not found (nothing to clear).")


def run_indexer():
    db_config = parse_db_config()
    db_manager = DatabaseManager(db_config)
    
    if not db_manager.create_table():
        print("Indexer cannot proceed: Database table could not be created or accessed.")
        return

    root_dirs = []
    print("\nEnter root directories to index (one per line, press Enter on empty line to finish):")
    while True:
        path = input(f"Enter path {len(root_dirs) + 1} (or press Enter to finish): ").strip()
        if not path:
            break
        if not os.path.isdir(path):
            print(f"Warning: '{path}' is not a valid directory or does not exist. Please enter a valid path.")
        else:
            root_dirs.append(os.path.abspath(path))

    if not root_dirs:
        print("No directories provided for indexing. Exiting indexer.")
        db_manager.close()
        return

    start_time = time.perf_counter()
    file_scanner = FileScanner(db_manager)
    
    # --- CRITICAL CHANGE FOR TQDM ---
    # Start the DB writer BEFORE scanning to immediately capture data
    db_manager.start_writer_thread(total_expected_files=0) # Start as indeterminate bar

    # Start scanning. The file_scanner will populate the queue.
    file_scanner.start_scanning(root_dirs) # This populates total_files_scanned

    # Now that scanning is complete and total_files_scanned is known,
    # update the tqdm total for the database writer.
    # This must happen BEFORE db_manager.wait_for_writer_thread()
    # to give the writer a chance to use the total.
    if db_manager.tqdm_instance:
        db_manager.tqdm_instance.total = file_scanner.total_files_scanned
        db_manager.tqdm_instance.refresh() # Ensure the total is immediately displayed
    # --- END CRITICAL CHANGE ---

    print("\nAll scanning tasks initiated. Waiting for database writes to complete...")
    db_manager.wait_for_writer_thread()

    end_time = time.perf_counter()
    print(f"\nTotal indexing duration: {end_time - start_time:.2f} seconds.")
    print(f"Indexed {file_scanner.total_files_scanned} files.")
    
    existing_roots = set(get_indexed_roots())
    new_roots = existing_roots.union(set(root_dirs))
    save_indexed_roots(list(new_roots))


def run_search():
    db_config = parse_db_config()
    search_manager = SearchManager(db_config)

    print("\n--- File Search ---")
    while True:
        search_term = input("Enter search term (or 'exit' to quit): ").strip()
        if search_term.lower() == 'exit':
            break

        search_type = input("Search by (filename/path/tags - default is filename): ").strip().lower()
        if search_type not in ['filename', 'path', 'tags']:
            search_type = 'filename'

        results = search_manager.search_files(search_term, search_type)
        search_manager.display_search_results(results)
        print("-" * 60)


def clear_index():
    db_config = parse_db_config()
    db_manager = DatabaseManager(db_config)
    
    print("\n--- Clear Index ---")
    confirm = input("Are you sure you want to clear ALL indexed files? This cannot be undone. (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        if db_manager.clear_all_indexes():
            clear_indexed_roots_file() 
            print("Index clearing process completed.")
        else:
            print("Index clearing failed.")
    else:
        print("Index clearing cancelled.")


def main():
    print("Welcome to the Multi-threaded File Indexer and Search!")
    while True:
        print("\nChoose an option:")
        print("1. Run Indexer")
        print("2. Run Search")
        print("3. Clear All Indexes") 
        print("4. Exit")              
        
        choice = input("Enter your choice (1/2/3/4): ").strip() 

        if choice == '1':
            run_indexer()
        elif choice == '2':
            run_search()
        elif choice == '3': 
            clear_index()
        elif choice == '4': 
            print("Exiting application. Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main()