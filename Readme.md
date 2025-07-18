# 🚀 FilEx : File Indexer & Search Tool

A multi-threaded Python application designed to quickly index files and folders on your local filesystem and enable fast, efficient searching via a MySQL database. Forget slow built-in searches – find your files in an instant!

## ✨ Features

* **Multi-threaded Indexing:** Utilizes Python's `threading` and `concurrent.futures` to scan multiple directories concurrently, speeding up the indexing process, especially for I/O-bound tasks.
* **MySQL Database Backend:** Stores file metadata (path, filename, size, dates) in a robust MySQL database for rapid querying.
* **Efficient Incremental Updates:** Uses `ON DUPLICATE KEY UPDATE` to intelligently add new files and update changed files without re-indexing everything from scratch.
* **Long Path Support:** Employs SHA-256 hashing for unique file paths, overcoming MySQL's index length limitations for very long file paths.
* **Navigable Search Results:** Provides clear, step-by-step paths for easy navigation to located files or folders.
* **Clear Index Option:** Easily wipe the entire index and start fresh.

---

## 🛠️ Setup & Installation

This guide will set up your development environment where your **Python application runs locally** and your **MySQL database runs in a Docker container**. This is a highly recommended and flexible setup.

### 1. Prerequisites

Before you begin, ensure you have:

* **Python 3.x:** (e.g., Python 3.9+) installed on your system.
* **Docker Desktop (Windows/macOS) or Docker Engine (Linux):** Installed and running. 

### 2. MySQL Database Setup (with Docker)

We'll use Docker Compose to manage your MySQL database container.

#### **Create `docker-compose.yml`**
Create a file named `docker-compose.yml` (no extension) in your **project's root directory** (`FilEx/`).

```yaml
services:
  db:
    image: mysql:8.0 
    container_name: file_indexer_db # A recognizable name for your database container
    environment:
      MYSQL_ROOT_PASSWORD: your_mysql_root_password # IMPORTANT: Set a strong root password for MySQL root user
      MYSQL_DATABASE: file_index_db                 # The database name your app will use
      MYSQL_USER: file_indexer_user                 # The username your app will use
      MYSQL_PASSWORD: your_strong_password          # The password for your app user
    ports:
      - "3306:3306" # Map container port 3306 to host port 3306
    volumes:
      - db_data:/var/lib/mysql # Persistent volume for MySQL data, so your index persists across container restarts

volumes:
  db_data: # Define the named volume for MySQL data persistence
```
#### Start the Database Container
- Open your terminal and navigate to the directory where your `docker-compose.yml` file is.

```bash
docker-compose up -d # -d runs the container in detached mode
```
- This will pull the `MySQL image`, create the `db_data` volume, and start the MySQL container. It might take a moment on the first run.

#### Verify Database is Running

```bash
docker compose ps
```
- You should see `file_indexer_db` listed with a Up status.

#### Initialize Database Schema
- Now, connect to this `Dockerized MySQL instance` from your host terminal and create your files table. The database will be accessible on `localhost:3306`.
```bash
mysql -h 127.0.0.1 -P 3306 -u file_indexer_user -p file_index_db
```
- Enter the `your_strong_password` you set in `docker-compose.yml` when prompted.

- Then, paste and execute your `CREATE TABLE` statement:
```SQL
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
```

- Exit the MySQL client: exit;

### 3. Python Application Setup (Local)

- Your Python application will run directly on your `host machine`.

#### Clone or Download Project
```bash
git clone https://github.com/alucard017/FilEx.git
cd FilEx
```
- If you haven't already, get your project files and place them in a directory (e.g., `FilEx/`).

#### Navigate to Project Root
- Open your terminal and navigate to the root directory of your `FilEx` project:


#### Create Required Directories
- Ensure the config and data directories exist:
```bash
mkdir -p config data
```
#### Configure Database Connection (config/db_config.ini)
- Open config/db_config.ini for editing:
```bash
nano config/db_config.ini
```

- Add the following content, ensuring the password matches what you set in `docker-compose.yml` for `file_indexer_user`:
```toml
[mysql]
host=localhost # Your local app connects to MySQL on localhost (via Docker's port mapping)
port=3306      # This matches the host port mapped in docker-compose.yml
user=file_indexer_user
password=your_strong_password
database=file_index_db
```
- Save and exit (Ctrl+O, Enter, Ctrl+X).

#### Create requirements.txt
- If you don't have it, create this file in your project root:
```bash
nano requirements.txt
```
- Add these lines:
```bash
mysql-connector-python
tqdm
```
- Save and exit.

#### Create and Activate a Python Virtual Environment (Recommended)
```
python3 -m venv venv  # Create a virtual environment named 'venv'
source venv/bin/activate  # Activate the virtual environment (Linux/macOS)
.\venv\Scripts\activate # Activate the virtual environment Windows
```
- You should see (venv) prepended to your terminal prompt.

#### Install Python Dependencies
- With your virtual environment active:
```bash
pip install -r requirements.txt
```
## 🚀 Usage

- Now you are ready to run your application!
- Ensure your Docker db container is running

```bash
docker compose ps
```
- Look for `file_indexer_db` with Up status. 
- If not, run: 
```bash
docker compose up -d.
```
- Run the application from your project's root directory:
```bash
python3 -m src.main
```
- You will be presented with the main menu:
```bash
Welcome to the Multi-threaded File Indexer and Search!

Choose an option:
1. Run Indexer
2. Run Search
3. Clear All Indexes
4. Exit
Enter your choice (1/2/3/4):
```
### 1. Run Indexer

    Select 1.

    Enter the absolute paths of the root directories on your host machine that you want to index (e.g., /home/alucard/Documents on Linux, or C:\Users\YourUser\Downloads on Windows).

    Press Enter after each path. Press Enter on an empty line to finish.

    The indexer will scan recursively, adding new files and updating existing ones. A progress bar will show the indexing status.

### 2. Run Search

    Select 2.

    Enter your search query (e.g., report.pdf, Q3_earnings, my_project).

    Specify whether to search by filename, path, or tags.

    Results will be displayed with navigable paths and full file paths for easy access.

### 3. Clear All Indexes

    Select 3.

    You'll be asked for confirmation. Type yes to permanently delete all indexed file metadata from your database and clear the data/indexed_roots.txt file. This cannot be undone.

### 4. Exit

    Select 4 to close the application.

## 💡 Notes

- Host Paths: When indexing, provide paths that exist on `your host machine (your computer)`, as your Python app runs locally.

- Permissions: Ensure your `local user account has read access` to all files and directories you intend to index.

- Stopping Docker DB: When you're done, you can stop the MySQL container:
```bash
docker compose stop db
```
- To remove it entirely (but keep the data volume for next time):
```bash
docker compose rm db
```
- To remove containers and delete all database data (start fresh next time):
```bash
docker compose down --volumes
```
- Deactivating Virtual Environment: When you're done working on the project, you can deactivate the Python virtual environment by simply typing: 
```bash
deactivate
```

## 🤝 Contributing

- Feel free to fork the repository, open issues, or submit pull requests for any improvements or bug fixes.

<!-- ## 📄 License

[Consider adding a license, e.g., MIT, GPL, etc.] -->