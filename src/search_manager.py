import os
import mysql.connector
from mysql.connector import Error
from .utils import parse_db_config, format_navigable_path

class SearchManager:
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection = None

    def connect(self):
        """Establishes a connection to the MySQL database."""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            if self.connection.is_connected():
                # print("SearchManager connected to MySQL.")
                return True
        except Error as e:
            print(f"Error connecting for search: {e}")
            self.connection = None
            return False
        return False

    def close(self):
        """Closes the database connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            # print("SearchManager connection closed.")

    def search_files(self, query, search_by='filename'):
        """
        Searches the database for files based on the query.
        """
        if not self.connect():
            print("Cannot search: Database connection failed.")
            return []

        results = []
        cursor = None
        try:
            cursor = self.connection.cursor(buffered=True) # Use buffered cursor for multiple rows
            
            # Basic sanitization: Use parameterized queries to prevent SQL injection
            if search_by == 'filename':
                sql = "SELECT filepath, filename FROM files WHERE filename LIKE %s"
            elif search_by == 'path':
                sql = "SELECT filepath, filename FROM files WHERE filepath LIKE %s"
            elif search_by == 'tags':
                sql = "SELECT filepath, filename FROM files WHERE tags LIKE %s"
            else:
                print("Invalid search_by criteria.")
                return []

            cursor.execute(sql, (f"%{query}%",))
            
            for (filepath, filename) in cursor:
                results.append({'filepath': filepath, 'filename': filename})
        except Error as e:
            print(f"Error during search query: {e}")
        finally:
            if cursor:
                cursor.close()
            self.close()
        return results

    def display_search_results(self, results):
        if not results:
            print("No files or folders found matching your query.")
            return

        print(f"\nFound {len(results)} results:")
        for result in results:
            filepath = result['filepath']
            filename = result['filename']
            
            print(f"\n--- Found: {filename} ---")
            print(f"  **Location:** {format_navigable_path(filepath)}")
            print(f"  **Full Path:** {filepath}")
            
            # Check if it's a directory or file (cannot check existence from DB alone reliably)
            # You might add a 'is_directory' column to your DB for this.
            # For now, we'll assume it's a file unless it's known to be a directory.
            # For improved usability, a better check would be needed, e.g., os.path.isdir(filepath)
            # but that would hit the filesystem, potentially slowing down display if many results.

            print(f"  To navigate, open File Explorer and copy the 'Full Path' and paste it into the address bar.")
            print(f"  Parent Folder: '{os.path.dirname(filepath)}'")
            print("=" * 60)