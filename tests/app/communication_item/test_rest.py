"""
Test CRUD endpoints for the CommunicationItem model.  These tests rely upon
preseeded rows in the communication_items table.
"""

import pytest
from app.models import CommunicationItem
from uuid import UUID, uuid4


#############
# Create
#############

@pytest.mark.parametrize("post_data,expected_status", [
    ({}, 400),
    ({"id": "invalid uuid4"}, 400),
    ({"id": "39247cfc-a52d-4b2b-b9a9-2ef8a20190cb"}, 400),
    ({"name": "communication item tests"}, 400),
    ({"va_profile_item_id": 5}, 400),
    ({"name": "communication item tests", "va_profile_item_id": 5}, 201),
    ({"default_send_indicator": False, "name": '', "va_profile_item_id": 5}, 400),
    ({"default_send_indicator": False, "name": "communication item tests", "va_profile_item_id": 5}, 201),
    ({"default_send_indicator": False, "name": "communication item tests", "va_profile_item_id": -5}, 400),
    ({"default_send_indicator": False, "name": "communication item tests", "va_profile_item_id": 0}, 400),
    (
        {
            "default_send_indicator": False,
            "id": "39247cfc-a52d-4b2b-b9a9-2ef8a20190cb",
            "name": "communication item tests",
            "va_profile_item_id": 5,
        },
        400
    ),
])
def test_create_communication_item(notify_db_session, admin_request, post_data, expected_status, worker_id):
    """
    The post data must contain "name" and "va_profile_item_id".  "default_send_indicatior" is optional.
    The post data must not contain "id".
    """

    if "name" in post_data and post_data["name"]:
        # Avoid duplicate names when running with multiple threads.
        post_data["name"] += (' ' + worker_id)

    if "va_profile_item_id" in post_data:
        # Avoid duplicate Profile IDs when running with multiple threads.
        post_data["va_profile_item_id"] += (int(worker_id[2:]) if (worker_id.startswith("gw")) else 0)

    response = admin_request.post(
        "communication_item.create_communication_item",
        post_data,
        expected_status
    )

    if expected_status == 201:
        assert isinstance(response, dict), response
        assert response["default_send_indicator"] is post_data.get("default_send_indicator", True)
        assert response["name"] == post_data["name"]
        assert response["va_profile_item_id"] == post_data["va_profile_item_id"]
        assert isinstance(UUID(response["id"]), UUID)

        communication_item = notify_db_session.session.get(CommunicationItem, response["id"])
        assert communication_item is not None

        # Test clean-up
        notify_db_session.session.delete(communication_item)
        notify_db_session.session.commit()
    elif expected_status == 400:
        assert isinstance(response, dict) and "errors" in response, response
        assert isinstance(response["errors"], list) and len(response["errors"]) == 1
        assert isinstance(response["errors"][0], dict)
        assert response["errors"][0]["error"] in ("DataError", "IntegrityError", "ValidationError")
        assert "message" in response["errors"][0]
    else:
        raise RuntimeError("This is a programming error.")


@pytest.mark.parametrize("post_data", [
        {"name": "COVID-19 Updates", "va_profile_item_id": 5},
        {"name": "name", "va_profile_item_id": 1},
    ],
    ids=(
        "existing name; new item ID",
        "new name; existing item ID",
    )
)
def test_create_communication_item_duplicates(notify_db_session, admin_request, post_data):
    """ The name and va_profile_item_id must be unique in the table. """

    response = admin_request.post(
        "communication_item.create_communication_item",
        post_data,
        400
    )

    assert isinstance(response, dict) and "errors" in response, response
    assert isinstance(response["errors"], list) and len(response["errors"]) == 1
    assert isinstance(response["errors"][0], dict)
    assert "error" in response["errors"][0]
    assert "message" in response["errors"][0]


#############
# Retrieve
#############

def test_get_all_communication_items(admin_request):
    response = admin_request.get("communication_item.get_all_communication_items", 200)
    assert isinstance(response["data"], list)

    for communication_item in response["data"]:
        assert isinstance(communication_item, dict)
        assert isinstance(communication_item["default_send_indicator"], bool)
        assert communication_item["default_send_indicator"], "Should be True by default."
        assert isinstance(communication_item["name"], str) and communication_item["name"]
        assert isinstance(communication_item["va_profile_item_id"], int)
        assert isinstance(UUID(communication_item["id"]), UUID)


def test_get_communication_item(notify_db_session, admin_request):
    response = admin_request.get(
        "communication_item.get_communication_item",
        200,
        communication_item_id="e2e35ef6-1ed1-4a02-9281-38f1c8afd2f6"
    )

    assert isinstance(response, dict), response
    assert isinstance(response["default_send_indicator"], bool)
    assert response["default_send_indicator"], "Should be True by default."
    assert response["name"] == "Board of Veterans' Appeals hearing reminder"
    assert response["va_profile_item_id"] == 1
    assert response["id"] == "e2e35ef6-1ed1-4a02-9281-38f1c8afd2f6"


@pytest.mark.parametrize("communication_item_id", ["doesn't exist", "39247cfc-a52d-4b2b-b9a9-2ef8a20190cb"])
def test_get_communication_item_not_found(notify_db_session, admin_request, communication_item_id):
    response = admin_request.get(
        "communication_item.get_communication_item",
        404,
        communication_item_id=communication_item_id
    )

    assert isinstance(response, dict), response


#############
# Update
#############

@pytest.mark.parametrize("post_data,expected_status", [
    ({}, 400),
    ({"name": 1}, 400),
    ({"name": ''}, 400),
    ({"name": "communication item tests"}, 200),
    ({"va_profile_item_id": "not a number"}, 400),
    ({"va_profile_item_id": -5}, 400),
    ({"va_profile_item_id": 0}, 400),
    ({"va_profile_item_id": 1}, 400),
    ({"name": "different name"}, 200),
    ({"va_profile_item_id": 600}, 200),
    ({"default_send_indicator": False}, 200),
    ({"name": "different name", "va_profile_item_id": 6, "default_send_indicator": False}, 200),
])
def test_partially_update_communication_item(notify_db_session, admin_request, post_data, expected_status, worker_id):
    va_profile_item_id = 5 + (int(worker_id[2:]) if (worker_id.startswith("gw")) else 0)
    name=f"communication item tests {worker_id}"
    communication_item = CommunicationItem(id=uuid4(), va_profile_item_id=va_profile_item_id, name=name)
    notify_db_session.session.add(communication_item)
    notify_db_session.session.commit()

    try:
        assert communication_item.default_send_indicator, "Should be True by default."

        response = admin_request.patch(
            "communication_item.partially_update_communication_item",
            post_data,
            expected_status,
            communication_item_id=str(communication_item.id)
        )

        assert isinstance(response, dict), response

        if expected_status == 200:
            if "name" in post_data:
                assert communication_item.name == post_data["name"]
                assert response["name"] == post_data["name"]
            if "va_profile_item_id" in post_data:
                assert communication_item.va_profile_item_id == post_data["va_profile_item_id"]
                assert response["va_profile_item_id"] == post_data["va_profile_item_id"]
            if "default_send_indicator" in post_data:
                assert isinstance(communication_item.default_send_indicator, bool)
                assert communication_item.default_send_indicator is post_data["default_send_indicator"]
                assert response["default_send_indicator"] is post_data["default_send_indicator"]
        elif expected_status == 400:
            assert response["errors"][0]["error"] in ("DataError", "IntegrityError", "ValidationError")
            assert "message" in response["errors"][0]
    finally:
        # Test clean-up
        print("MADE IT HERE")
        notify_db_session.session.delete(communication_item)
        notify_db_session.session.commit()


@pytest.mark.parametrize("communication_item_id", ["doesn't exist", "39247cfc-a52d-4b2b-b9a9-2ef8a20190cb"])
def test_partially_update_communication_item_not_found(notify_db_session, admin_request, communication_item_id):
    admin_request.patch(
        "communication_item.partially_update_communication_item",
        {"va_profile_item_id": 2},
        404,
        communication_item_id=communication_item_id
    )


#############
# Delete
#############

def test_delete_communication_item(notify_db_session, admin_request):
    communication_item = CommunicationItem(id=uuid4(), va_profile_item_id=5, name="communication item tests")
    communication_item_id = communication_item.id
    notify_db_session.session.add(communication_item)
    notify_db_session.session.commit()

    # Ensure the new CommunicationItem instance is in the database.
    assert CommunicationItem.query.get(communication_item_id) is not None

    admin_request.delete(
        "communication_item.delete_communication_item",
        202,
        communication_item_id=communication_item_id
    )

    # Ensure communication_item1 is not in the database.
    assert CommunicationItem.query.get(communication_item_id) is None


@pytest.mark.parametrize("communication_item_id", ["doesn't exist", "39247cfc-a52d-4b2b-b9a9-2ef8a20190cb"])
def test_delete_communication_item_not_found(notify_db_session, admin_request, communication_item_id):
    response = admin_request.delete(
        "communication_item.delete_communication_item",
        404,
        communication_item_id=communication_item_id
    )

    assert isinstance(response, dict), response
