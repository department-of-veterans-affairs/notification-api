"""Add encrypted_va_profile_opt_in_out stored function.

Revision ID: 0384_encrypt_opt_in_out
Revises: 0383_add_blind_index
Create Date: 2026-02-19 23:31:34.738331
"""

from alembic import op

revision = '0384_encrypt_opt_in_out'
down_revision = '0383_add_blind_index'


def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION public.encrypted_va_profile_opt_in_out(_va_profile_id integer, _encrypted_va_profile_id text, _encrypted_va_profile_id_blind_index text, _communication_item_id integer, _communication_channel_id integer, _allowed boolean, _source_datetime timestamp without time zone)
        RETURNS boolean 
        LANGUAGE plpgsql
        AS $function$
        DECLARE number_of_changed_records int;
        BEGIN
        -- Try to INSERT new record
        INSERT INTO va_profile_local_cache(va_profile_id, encrypted_va_profile_id, encrypted_va_profile_id_blind_index, communication_item_id, communication_channel_id, source_datetime, allowed)
            VALUES (_va_profile_id, _encrypted_va_profile_id, _encrypted_va_profile_id_blind_index, _communication_item_id, _communication_channel_id, _source_datetime, _allowed)
            -- Must have unique combo of (va_profile_id, communication_item_id, communication_channel_id)
            -- If this unique combo already exists -> UPDATE
            ON CONFLICT ON CONSTRAINT uix_veteran_id DO UPDATE
            -- Given satisfied WHERE clause below, always SET (allowed, source_datetime) 
            SET allowed = EXCLUDED.allowed, source_datetime = EXCLUDED.source_datetime,
                -- conditionally SET (encrypted_va_profile_id, encrypted_va_profile_id_blind_index)
                -- Only UPGRADE encrypted fields when NOT a blind-index match
                -- NOTE: these fields are nullable, so we consider the following:
                -- MATCH on blind-index = same underlying plaintext = no re-encryption needed, keep existing.
                -- NO MATCH on blind index = record is being migrated to a new encryption key
                encrypted_va_profile_id =
                    CASE
                        -- if MATCH on blind-index, then keep the existing encrypted_va_profile_id (no change)
                        WHEN va_profile_local_cache.encrypted_va_profile_id_blind_index
                             = EXCLUDED.encrypted_va_profile_id_blind_index
                        THEN va_profile_local_cache.encrypted_va_profile_id
                        -- if NO MATCH on blind-index, then use the new encrypted_va_profile_id (update)
                        ELSE EXCLUDED.encrypted_va_profile_id
                    END,
            
                encrypted_va_profile_id_blind_index = 
                    CASE
                        -- if MATCH on blind-index, then keep the existing encrypted_va_profile_id (no change)
                        WHEN va_profile_local_cache.encrypted_va_profile_id_blind_index = EXCLUDED.encrypted_va_profile_id_blind_index
                        THEN va_profile_local_cache.encrypted_va_profile_id_blind_index
                        -- if NO MATCH on blind-index, then use the new encrypted_va_profile_id_blind_index (update)
                        ELSE EXCLUDED.encrypted_va_profile_id_blind_index
                    END
            WHERE
                -- UPDATE only if source_datetime is newer than existing
                EXCLUDED.source_datetime > va_profile_local_cache.source_datetime;
        GET DIAGNOSTICS number_of_changed_records = ROW_COUNT; 
        RETURN number_of_changed_records > 0;
        END;
        $function$;
    """)


def downgrade():
    op.execute(
        'DROP FUNCTION IF EXISTS '
        'encrypted_va_profile_opt_in_out(integer, text, text, integer, integer, boolean, timestamp without time zone);'
    )
