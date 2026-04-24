#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# Copyright (C) 2025 New Vector, Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl_3.0.html>.
#
#

from typing import Any
from unittest.mock import AsyncMock

from twisted.internet import defer
from twisted.test.proto_helpers import MemoryReactor

import synapse.rest.admin
from synapse.api.errors import RequestSendFailed
from synapse.rest.client import login, register, user_directory
from synapse.server import HomeServer
from synapse.types import JsonMapping
from synapse.util.clock import Clock

from tests import unittest


class UserDirectorySearchTestCase(unittest.HomeserverTestCase):
    servlets = [
        user_directory.register_servlets,
        synapse.rest.admin.register_servlets,
        login.register_servlets,
        register.register_servlets,
    ]

    user_directory_handler: Any
    search_users_mock: Any
    bob_token: Any
    alice_token: Any

    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        config = self.default_config()
        config["user_directory"] = {"enabled": True, "search_all_users": True}
        config["federation_domain_whitelist"] = ["test", "test2", "test3"]
        return self.setup_test_homeserver(config=config)

    def prepare(
        self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer
    ) -> None:
        # Initialize instance variables
        self.user_directory_handler = homeserver.get_user_directory_handler()

        # Create test users
        self.register_user("alice", "password")
        self.register_user("bob", "password")
        self.register_user("charlie", "password")

        # Mock the search_users method to return controlled results
        self.search_users_mock = AsyncMock()
        self.user_directory_handler.search_users = self.search_users_mock
        self.federation_client_user_directory_search_mock = AsyncMock()
        self.user_directory_handler.federation_client.transport_layer.user_directory_search = self.federation_client_user_directory_search_mock

        # Create access tokens for testing
        self.bob_token = self.get_success(
            homeserver.get_auth_handler().create_access_token_for_user_id(
                "@bob:test", device_id=None, valid_until_ms=None
            )
        )
        self.alice_token = self.get_success(
            homeserver.get_auth_handler().create_access_token_for_user_id(
                "@alice:test", device_id=None, valid_until_ms=None
            )
        )

    def test_search_users(self) -> None:
        """Test that a search without a token works as expected."""
        # Set up the mock to return some results
        self.search_users_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                # Local homeserver may have discovered this user
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                },
            ],
        }

        async def mock_federation(
            requester: str, destination: str, search_term: str, limit: int
        ) -> JsonMapping:
            if destination == "test2":
                return {
                    "limited": False,
                    "results": [
                        {
                            "user_id": "@john-marvelous:test2",
                            "display_name": "John Marvelous",
                            "avatar_url": "mxc://test2/john-marvelous",
                        }
                    ],
                }
            else:
                return {"limited": False, "results": []}

        self.federation_client_user_directory_search_mock.side_effect = mock_federation

        # Make a request to the search endpoint
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(
            channel.json_body,
            {
                "limited": False,
                "results": [
                    {
                        "user_id": "@alice:test",
                        "display_name": "Alice",
                        "avatar_url": None,
                    },
                    {
                        "user_id": "@john-marvelous:test2",
                        "display_name": "John Marvelous",
                        "avatar_url": "mxc://test2/john-marvelous",
                    },
                ],
            },
        )

        # Check that the search_users method was called with the correct arguments
        self.search_users_mock.assert_called_once_with("@bob:test", "alice", 10)
        self.federation_client_user_directory_search_mock.assert_any_call(
            "@bob:test", "test2", "alice", 10
        )
        self.federation_client_user_directory_search_mock.assert_any_call(
            "@bob:test", "test3", "alice", 10
        )
        self.assertEqual(
            self.federation_client_user_directory_search_mock.call_count, 2
        )

    def test_search_users_with_timeout(self) -> None:
        """Test that a search without a token works as expected."""
        # Set up the mock to return some results
        self.search_users_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                }
            ],
        }

        async def mock_federation(
            requester: str, destination: str, search_term: str, limit: int
        ) -> JsonMapping:
            if destination == "test2":
                return {
                    "limited": False,
                    "results": [
                        {
                            "user_id": "@john-marvelous:test2",
                            "display_name": "John Marvelous",
                            "avatar_url": "mxc://test2/john-marvelous",
                        }
                    ],
                }
            else:
                raise RequestSendFailed(
                    defer.TimeoutError("Timed out after 2 seconds"),
                    can_retry=False,
                )

        self.federation_client_user_directory_search_mock.side_effect = mock_federation

        # Make a request to the search endpoint
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(
            channel.json_body,
            {
                "limited": False,
                "results": [
                    {
                        "user_id": "@alice:test",
                        "display_name": "Alice",
                        "avatar_url": None,
                    },
                    {
                        "user_id": "@john-marvelous:test2",
                        "display_name": "John Marvelous",
                        "avatar_url": "mxc://test2/john-marvelous",
                    },
                ],
            },
        )

        # Check that the search_users method was called with the correct arguments
        self.search_users_mock.assert_called_once_with("@bob:test", "alice", 10)
        self.federation_client_user_directory_search_mock.assert_any_call(
            "@bob:test", "test2", "alice", 10
        )
        self.federation_client_user_directory_search_mock.assert_any_call(
            "@bob:test", "test3", "alice", 10
        )
        self.assertEqual(
            self.federation_client_user_directory_search_mock.call_count, 2
        )

    def test_search_with_limit(self) -> None:
        """Test that a search with a limit works as expected."""
        # Set up the mock to return some results
        self.search_users_mock.return_value = {
            "limited": True,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                }
            ],
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [],
        }

        # Make a request to the search endpoint with a limit
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "limit": 5},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], False)
        self.assertEqual(len(channel.json_body["results"]), 1)

        # Check that the search_users method was called with the correct arguments
        self.search_users_mock.assert_called_once_with("@bob:test", "alice", 5)

    def test_multiple_pending_searches(self) -> None:
        """Test that multiple pending searches with the same token all get notified."""
        # Set up the mock to return some results for the initial search
        self.search_users_mock.return_value = {
            "limited": True,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                }
            ],
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [],
        }

        # Make an initial request
        self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test"},
            access_token=self.bob_token,
        )

        # Set up the mock for the follow-up searches with token
        # We'll use a side effect to return different results for each call
        results_for_bob = {
            "limited": False,
            "results": [
                {
                    "user_id": "@charlie:test",
                    "display_name": "Charlie",
                    "avatar_url": None,
                }
            ],
        }

        results_for_alice = {
            "limited": False,
            "results": [
                {
                    "user_id": "@charlie:test",
                    "display_name": "Charlie",
                    "avatar_url": None,
                }
            ],
        }

        # Mock the get_federated_search_results method to return results
        get_federated_results_mock = AsyncMock()
        get_federated_results_mock.side_effect = [results_for_bob, results_for_alice]
        self.user_directory_handler.get_federated_search_results = (
            get_federated_results_mock
        )

        # Make multiple requests to the search endpoint with the same token
        channel1 = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test"},
            access_token=self.bob_token,
        )

        channel2 = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test"},
            access_token=self.alice_token,
        )

        # Check that both responses are correct
        self.assertEqual(channel1.code, 200)
        self.assertEqual(channel2.code, 200)

        # Check that get_federated_search_results was called twice, once for each request
        self.assertEqual(get_federated_results_mock.call_count, 2)
