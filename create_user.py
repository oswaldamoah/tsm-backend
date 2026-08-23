import os
import sys
import bcrypt
import psycopg2
from dotenv import load_dotenv

# 1. Load Environment Variables from your .env file
load_dotenv()

# Read the DATABASE_URL variable
NEON_DATABASE_URL = os.getenv("DATABASE_URL")

if not NEON_DATABASE_URL:
    print("❌ Error: 'DATABASE_URL' not found in your environment or .env file.")
    sys.exit(1)

# 2. Collect Inputs
username = input("Enter username: ")
email = input("Enter email: ")
password = input("Enter password: ")
role = input("Enter role (manager/admin) [default: manager]: ") or "manager"
role = role.strip().upper()

# 3. Hash Password using pure bcrypt
password_bytes = password.encode('utf-8')
salt = bcrypt.gensalt(rounds=12)
hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

# 4. Direct SQL Database Injection
query = """
INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at, updated_at) 
VALUES (gen_random_uuid(), %s, %s, %s, %s, true, now(), now());
"""

try:
    conn = psycopg2.connect(NEON_DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(query, (username, email, hashed_password, role))
    conn.commit()
    print(f"\n✨ Successfully created user '{username}' directly in Neon!")
except Exception as e:
    print(f"\n❌ Error: {e}")
finally:
    if 'conn' in locals(): 
        conn.close()
