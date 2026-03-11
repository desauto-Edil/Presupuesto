-- ===========================================================================
-- setup_postgres.sql
-- Script SQL para crear base de datos y usuario en PostgreSQL (desarrollo local)
--
-- Uso:
--   psql -U postgres -f docs/setup_postgres.sql
-- ===========================================================================

-- 1. Crear usuario de la aplicación
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'imperandina_user') THEN
        CREATE USER imperandina_user WITH PASSWORD 'cambia_esta_password';
        RAISE NOTICE 'Usuario imperandina_user creado.';
    ELSE
        RAISE NOTICE 'Usuario imperandina_user ya existe.';
    END IF;
END
$$;

-- 2. Permitir creación de bases de datos (requerido para tests de Django)
ALTER USER imperandina_user CREATEDB;

-- 3. Crear base de datos
SELECT 'CREATE DATABASE presupuestos OWNER imperandina_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'presupuestos')\gexec

-- 4. Conectar y otorgar permisos
\c presupuestos

GRANT ALL PRIVILEGES ON DATABASE presupuestos TO imperandina_user;
GRANT ALL ON SCHEMA public TO imperandina_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO imperandina_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO imperandina_user;

-- 5. Verificación
\echo 'Base de datos presupuestos configurada correctamente.'
\echo 'Usuario: imperandina_user'
\echo 'Base: presupuestos'
\du imperandina_user
\l presupuestos
