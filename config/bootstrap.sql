\set ON_ERROR_STOP on
\getenv app_password TEMPORAL_DB_PASSWORD
SELECT format('CREATE ROLE temporal LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'temporal')
\gexec
ALTER ROLE temporal PASSWORD :'app_password';
GRANT temporal TO temporal_admin;
SELECT 'CREATE DATABASE temporal OWNER temporal'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'temporal')
\gexec
SELECT 'CREATE DATABASE temporal_visibility OWNER temporal'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'temporal_visibility')
\gexec
