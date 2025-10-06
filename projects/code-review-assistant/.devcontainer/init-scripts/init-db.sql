-- Initialize Code Review Assistant database
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create tables for code review assistant if they don't exist
-- This will be populated by the application's migration system