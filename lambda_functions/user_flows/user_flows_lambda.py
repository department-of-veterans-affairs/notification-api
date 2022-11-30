import pytest


def user_flows_handler(event, context):
    environment = event['environment']

    return pytest.main([
        "-p", "no:cacheprovider",
        "-s", "--verbose",
        # below can be used to suppress output
        # "--tb=short",
        "--environment", environment,
        "./test_retrieve_everything.py"
    ])
