import os
import datetime

def get_file_metadata(filepath):
    """
    Extracts basic metadata for a given file path.
    Returns None if file is inaccessible.
    """
    try:
        stat_info = os.stat(filepath)
        filename = os.path.basename(filepath)
        extension = os.path.splitext(filename)[1].lower()
        if extension.startswith('.'):
            extension = extension[1:] # Remove leading dot

        # Timestamps are often floats (seconds since epoch) in os.stat
        # Convert to milliseconds for BIGINT storage in MySQL
        creation_time_ms = int(stat_info.st_ctime * 1000)
        modification_time_ms = int(stat_info.st_mtime * 1000)

        return {
            'filepath': filepath,
            'filename': filename,
            'extension': extension,
            'size': stat_info.st_size,
            'creation_time': creation_time_ms,
            'modification_time': modification_time_ms,
            'tags': '' # Default empty tags
        }
    except FileNotFoundError:
        # print(f"Warning: File not found during metadata collection: {filepath}")
        return None
    except OSError as e:
        # print(f"Warning: OS Error accessing {filepath}: {e}")
        return None
    except Exception as e:
        # print(f"Warning: Unexpected error with {filepath}: {e}")
        return None

def parse_db_config(config_file='config/db_config.ini'):
    """Parses database configuration from an INI file."""
    import configparser
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
        db_config = config['mysql']
        return {
            'host': db_config.get('host', 'localhost'),
            'port': db_config.getint('port', 3306),
            'user': db_config.get('user'),
            'password': db_config.get('password'),
            'database': db_config.get('database')
        }
    except Exception as e:
        print(f"Error parsing database configuration: {e}")
        print("Please ensure config/db_config.ini exists and is correctly formatted.")
        exit(1)

def format_navigable_path(filepath):
    """
    Splits a full file path into its components for easier navigation,
    similar to what we discussed previously.
    """
    parts = []
    current_path = filepath
    
    # Handle drive letters for Windows
    if os.path.splitdrive(current_path)[0]:
        parts.append(os.path.splitdrive(current_path)[0])
        current_path = os.path.splitdrive(current_path)[1]

    # Split the remaining path by directory separators
    while True:
        parent, name = os.path.split(current_path)
        if name:
            parts.insert(0, name) # Insert at the beginning to reverse order
        if not parent or parent == os.path.sep: # Stop when we reach the root or empty
            if parent == os.path.sep: # Add the root separator if present
                parts.insert(0, os.path.sep)
            break
        current_path = parent
    
    parts = [part for part in parts if part] # Remove empty strings

    nav_output = []
    if parts:
        if parts[0].endswith(':') or parts[0] == os.path.sep:
            nav_output.append(f"{parts[0]}")
            start_index = 1
        else:
            start_index = 0

        for i in range(start_index, len(parts)):
            if i == len(parts) - 1:
                nav_output.append(f"'{parts[i]}'")
            else:
                nav_output.append(f"'{parts[i]}'")
    
    return " -> ".join(nav_output)