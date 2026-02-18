"""Update va_profile_opt_in_out stored function to accept encrypted_va_profile_id

Revision ID: 0385_remove_stored_proc_backfill
Revises: 0384_encrypt_opt_in_out
Create Date: 2026-02-18 10:29:34.738331
"""

from alembic import op


revision = '0385_remove_stored_proc_backfill'
down_revision = '0384_encrypt_opt_in_out'


def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION public.va_profile_opt_in_out(
            _va_profile_id integer,
            _encrypted_va_profile_id text,
            _encrypted_va_profile_id_blind_index text,
            _communication_item_id integer,
            _communication_channel_id integer,
            _allowed boolean,
            _source_datetime timestamp without time zone
        )
        RETURNS boolean
        LANGUAGE plpgsql
        AS $function$
        DECLARE 
            changed_upsert int;
        BEGIN
            INSERT INTO va_profile_local_cache(va_profile_id, encrypted_va_profile_id, encrypted_va_profile_id_blind_index, communication_item_id, communication_channel_id, source_datetime, allowed)
            VALUES(_va_profile_id, _encrypted_va_profile_id, _encrypted_va_profile_id_blind_index, _communication_item_id, _communication_channel_id, _source_datetime, _allowed)
            ON CONFLICT ON CONSTRAINT uix_veteran_id DO UPDATE
            SET allowed = _allowed, source_datetime = _source_datetime
            WHERE _source_datetime > va_profile_local_cache.source_datetime
                AND va_profile_local_cache.va_profile_id = _va_profile_id
                AND va_profile_local_cache.communication_item_id = _communication_item_id
                AND va_profile_local_cache.communication_channel_id = _communication_channel_id;
            
            GET DIAGNOSTICS changed_upsert = ROW_COUNT;
             
        RETURN (changed_upsert > 0);
        END;
        $function$;
    """)


def downgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION public.va_profile_opt_in_out(
            _va_profile_id integer,
            _encrypted_va_profile_id text,
            _encrypted_va_profile_id_blind_index text,
            _communication_item_id integer,
            _communication_channel_id integer,
            _allowed boolean,
            _source_datetime timestamp without time zone
        )
        RETURNS boolean
        LANGUAGE plpgsql
        AS $function$
        DECLARE 
            changed_upsert int;
            changed_backfill int;
        BEGIN
            INSERT INTO va_profile_local_cache(va_profile_id, encrypted_va_profile_id, encrypted_va_profile_id_blind_index, communication_item_id, communication_channel_id, source_datetime, allowed)
            VALUES(_va_profile_id, _encrypted_va_profile_id, _encrypted_va_profile_id_blind_index, _communication_item_id, _communication_channel_id, _source_datetime, _allowed)
            ON CONFLICT ON CONSTRAINT uix_veteran_id DO UPDATE
            SET allowed = _allowed, source_datetime = _source_datetime
            WHERE _source_datetime > va_profile_local_cache.source_datetime
                AND va_profile_local_cache.va_profile_id = _va_profile_id
                AND va_profile_local_cache.communication_item_id = _communication_item_id
                AND va_profile_local_cache.communication_channel_id = _communication_channel_id;
            
            GET DIAGNOSTICS changed_upsert = ROW_COUNT;
             
            -- Backfill blind index for ALL rows for this va_profile_id
        IF changed_upsert > 0 THEN UPDATE va_profile_local_cache
            SET encrypted_va_profile_id = COALESCE(encrypted_va_profile_id, _encrypted_va_profile_id), encrypted_va_profile_id_blind_index = COALESCE(encrypted_va_profile_id_blind_index, _encrypted_va_profile_id_blind_index)
            WHERE va_profile_id = _va_profile_id
            AND (encrypted_va_profile_id IS NULL OR encrypted_va_profile_id_blind_index IS NULL);
    
            GET DIAGNOSTICS changed_backfill = ROW_COUNT;
            RAISE NOTICE 'va_profile_opt_in_out backfill updated % row(s) for va_profile_id %', changed_backfill, _va_profile_id;
        END IF;
        RETURN (changed_upsert > 0);
        END;
        $function$;
    """)
