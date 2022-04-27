-- Run these stored procedures when the VA Notify infrastructure receives
-- an opt-in or opt-out notification from VA Profile.


CREATE OR REPLACE PROCEDURE va_profile_opt_in (_mpi_icn varchar(29), _va_profile_id integer, _communication_item_id integer, _communication_channel_name varchar(255))
    LANGUAGE sql AS $$
        INSERT INTO va_profile_local_cache (mpi_icn, va_profile_id, communication_item_id, communication_channel_name)
        VALUES (_mpi_icn, _va_profile_id, _communication_item_id, _communication_channel_name)
        ON CONFLICT DO NOTHING;
    $$;


CREATE OR REPLACE PROCEDURE va_profile_opt_out (_va_profile_id integer, _communication_item_id integer, _communication_channel_name varchar(255))
    LANGUAGE sql AS $$
       DELETE FROM va_profile_local_cache
       WHERE va_profile_id = _va_profile_id AND communication_item_id = _communication_item_id AND communication_channel_name = _communication_channel_name;
    $$;
