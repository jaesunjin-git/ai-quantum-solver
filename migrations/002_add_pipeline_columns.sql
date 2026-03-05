-- ============================================================
-- Migration 002: Add pipeline columns to core.session_states
-- Created: TASK 7 (Pipeline & Session schema update)
-- 
-- 실행 방법:
--   psql -U postgres -d quantum_db -f migrations/002_add_pipeline_columns.sql
--
-- 주의: 각 ALTER TABLE은 IF NOT EXISTS가 없으므로
--       이미 존재하는 컬럼은 에러 발생 → DO $$ 블록으로 안전 처리
-- ============================================================

DO $$
BEGIN
    -- Problem Definition Phase
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='problem_defined') THEN
        ALTER TABLE core.session_states ADD COLUMN problem_defined BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='problem_definition') THEN
        ALTER TABLE core.session_states ADD COLUMN problem_definition TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='confirmed_problem') THEN
        ALTER TABLE core.session_states ADD COLUMN confirmed_problem TEXT;
    END IF;

    -- Data Normalization Phase
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='data_normalized') THEN
        ALTER TABLE core.session_states ADD COLUMN data_normalized BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='normalization_mapping') THEN
        ALTER TABLE core.session_states ADD COLUMN normalization_mapping TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='normalized_data_summary') THEN
        ALTER TABLE core.session_states ADD COLUMN normalized_data_summary TEXT;
    END IF;

    -- Structural Normalization Phase 1
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='structural_normalization_done') THEN
        ALTER TABLE core.session_states ADD COLUMN structural_normalization_done BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='phase1_summary') THEN
        ALTER TABLE core.session_states ADD COLUMN phase1_summary TEXT;
    END IF;

    -- Constraint Confirmation
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='constraints_confirmed') THEN
        ALTER TABLE core.session_states ADD COLUMN constraints_confirmed BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='confirmed_constraints') THEN
        ALTER TABLE core.session_states ADD COLUMN confirmed_constraints TEXT;
    END IF;

    -- Data Facts
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='core' AND table_name='session_states' AND column_name='data_facts') THEN
        ALTER TABLE core.session_states ADD COLUMN data_facts TEXT;
    END IF;

    -- Data schema (if not exists)
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'data') THEN
        CREATE SCHEMA data;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'model') THEN
        CREATE SCHEMA model;
    END IF;

    RAISE NOTICE 'Migration 002 completed successfully.';
END $$;