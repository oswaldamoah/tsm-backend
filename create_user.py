import os
import sys
import bcrypt
import psycopg2
from dotenv import load_dotenv

# 1. Load Environment Variables from your local .env file
load_dotenv()

# Read the DATABASE_URL variable
NEON_DATABASE_URL = os.getenv("DATABASE_URL")

# Safe Gate: If running in GitHub Actions/Repo environment without a .env file,
# it will stop here cleanly instead of throwing a strange Bcrypt error.
if not NEON_DATABASE_URL:
    print("\n⚠️ Environment Note: 'DATABASE_URL' not detected.")
    print("If you are running this locally, make sure your .env file exists.")
    print("If this is an automated GitHub test/push action, skipping execution.")
    sys.exit(0) # Exit cleanly with code 0 so your GitHub push/workflow succeeds

# 2. Collect Inputs (Only runs locally where DATABASE_URL exists)
print("--- Neon User Creation Utility ---")
username = input("Enter username: ")
email = input("Enter email: ")
password = input("Enter password: ")

role = input("Enter role (MANAGER/ADMIN) [default: MANAGER]: ") or "MANAGER"
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
