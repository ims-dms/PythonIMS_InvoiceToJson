import json
import pyodbc

# Mapping of possible keys to standard keys
KEY_MAPPING = {
    "server": ["data source", "server", "data_source"],
    "database": ["initial catalog", "database", "initial_catalog", "inital"],
    "user": ["user", "user id", "userid", "user_id", "id", "uid", "userId", "User_Id", "UserId"],
    "password": ["password", "pwd", "pass", "PASSWORD", "Password"]
}

def normalize_keys(config: dict) -> dict:
    normalized = {}
    lower_config = {k.lower(): v for k, v in config.items()}
    for std_key, aliases in KEY_MAPPING.items():
        for alias in aliases:
            if alias.lower() in lower_config:
                normalized[std_key] = lower_config[alias.lower()]
                break
    return normalized

def get_connection(connection_params: dict = None):
    if connection_params is None:
        # Read connection details from DBConnection.txt
        with open('DBConnection.txt', 'r') as f:
            config = json.load(f)
    else:
        config = connection_params

    normalized_config = normalize_keys(config)

    server = normalized_config.get("server")
    database = normalized_config.get("database")
    user = normalized_config.get("user")
    password = normalized_config.get("password")

    # Build connection string for SQL Server using pyodbc
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password}"
    )

    try:
        connection = pyodbc.connect(conn_str)
        print("Database connection successful")
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise

if __name__ == "__main__":
    # Test the connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    print("SQL Server version:", row[0])
    conn.close()
