import json
import pyodbc

def get_connection():
    # Read connection details from DBConnection.txt
    with open('DBConnection.txt', 'r') as f:
        config = json.load(f)

    user = config.get("USER")
    server = config.get("SERVER")
    password = config.get("PASSWORD")
    database = config.get("DATABASE")

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
