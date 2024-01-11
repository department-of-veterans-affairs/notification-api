from sqlalchemy import select

from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import (
    dao_delete_template_folder,
    dao_get_template_folder_by_id_and_service_id,
    dao_get_valid_template_folders_by_id,
    dao_update_template_folder,
)
from app.models import user_folder_permissions
from tests.app.db import create_template_folder


def test_dao_get_template_folder_by_id_and_service_id(sample_user, sample_service):
    service = sample_service()
    folder = create_template_folder(service)

    template_folder_from_db = dao_get_template_folder_by_id_and_service_id(folder.id, service.id)
    assert template_folder_from_db.id == folder.id


def test_dao_get_valid_template_folders_by_id(sample_service):
    service = sample_service()
    folder1 = create_template_folder(service)
    folder2 = create_template_folder(service)

    template_folders = dao_get_valid_template_folders_by_id([folder1.id, folder2.id])
    assert frozenset((template_folders[0].id, template_folders[1].id)) == frozenset((folder1.id, folder2.id))


def test_dao_delete_template_folder_deletes_user_folder_permissions(notify_db_session, sample_service):
    service = sample_service()
    folder = create_template_folder(service)
    folder_id = folder.id
    service_user = dao_get_service_user(service.created_by_id, service.id)
    folder.users = [service_user]

    dao_update_template_folder(folder)
    dao_delete_template_folder(folder)

    stmt = select(user_folder_permissions).where(user_folder_permissions.c.template_folder_id == folder_id)
    assert notify_db_session.session.execute(stmt).all() == []
