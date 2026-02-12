"""Update va_profile_opt_in_out stored function to accept encrypted_va_profile_id

Revision ID: 0384_encrypt_opt_in_out
Revises: 0383_add_blind_index
Create Date: 2026-02-09 23:31:34.738331
"""

from alembic import op
import sqlalchemy as sa


revision = '0384_encrypt_opt_in_out'
down_revision = '0383_add_blind_index'


def upgrade():
    op.execute(
        'DROP FUNCTION IF EXISTS '
        'va_profile_opt_in_out(integer, integer, integer, boolean, timestamp without time zone);'
    )
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
        END IF;
        RETURN (changed_upsert > 0);
        END;
        $function$;
    """)


def downgrade():
    op.execute(
        'DROP FUNCTION IF EXISTS '
        'va_profile_opt_in_out(integer, text, integer, integer, boolean, timestamp without time zone);'
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION public.va_profile_opt_in_out(
            _va_profile_id integer,
            _communication_item_id integer,
            _communication_channel_id integer,
            _allowed boolean,
            _source_datetime timestamp without time zone
        )
        RETURNS boolean
        LANGUAGE plpgsql
        AS $function$
        DECLARE number_of_changed_records Int;
        BEGIN
            INSERT INTO va_profile_local_cache(va_profile_id, communication_item_id, communication_channel_id, source_datetime, allowed)
                VALUES(_va_profile_id, _communication_item_id, _communication_channel_id, _source_datetime, _allowed)
                    ON CONFLICT ON CONSTRAINT uix_veteran_id DO UPDATE
                SET allowed = _allowed, source_datetime = _source_datetime
                WHERE _source_datetime > va_profile_local_cache.source_datetime
                    AND va_profile_local_cache.va_profile_id = _va_profile_id
                    AND va_profile_local_cache.communication_item_id = _communication_item_id
                    AND va_profile_local_cache.communication_channel_id = _communication_channel_id;
            GET DIAGNOSTICS number_of_changed_records = ROW_COUNT;
            RETURN number_of_changed_records > 0;
        END;
        $function$;
    """)
