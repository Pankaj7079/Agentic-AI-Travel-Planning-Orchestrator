CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- parikrama user should already exist if using POSTGRES_USER
-- but we make sure the vector extension is available.
