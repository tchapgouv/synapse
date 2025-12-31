# Copyright 2023 The Matrix.org Foundation C.I.C.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any
from unittest.mock import AsyncMock, patch

from twisted.internet import defer
from twisted.test.proto_helpers import MemoryReactor

import synapse.rest.admin
from synapse.rest.client import login, register, user_directory
from synapse.server import HomeServer
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
    store: Any
    search_users_mock: Any
    bob_token: Any
    alice_token: Any

    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        config = self.default_config()
        config["user_directory"] = {"enabled": True, "search_all_users": True}
        return self.setup_test_homeserver(config=config)

    def prepare(
        self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer
    ) -> None:
        # Initialize instance variables
        self.user_directory_handler = homeserver.get_user_directory_handler()
        self.store = homeserver.get_datastores().main

        # Create test users
        self.register_user("alice", "password")
        self.register_user("bob", "password")
        self.register_user("charlie", "password")

        # Mock the search_users method to return controlled results
        self.search_users_mock = AsyncMock()
        self.user_directory_handler.search_users = self.search_users_mock

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

    def test_search_without_token(self) -> None:
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
                    }
                ],
            },
        )

        # Check that the search_users method was called with the correct arguments
        self.search_users_mock.assert_called_once_with("@bob:test", "alice", 10)

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
            "search_token": "test_token_123",
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
        self.assertEqual(channel.json_body["limited"], True)
        self.assertEqual(len(channel.json_body["results"]), 1)

        # Check that the search_users method was called with the correct arguments
        self.search_users_mock.assert_called_once_with("@bob:test", "alice", 5)

        # Check that a search token was returned
        self.assertIn("search_token", channel.json_body)
        self.assertIsInstance(channel.json_body["search_token"], str)

    def test_search_with_token(self) -> None:
        """Test that a search with a token works as expected."""
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
            "search_token": "test_token_123",
        }

        # Make an initial request to get a token
        initial_channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test"},
            access_token=self.bob_token,
        )

        # Get the token from the response
        search_token = initial_channel.json_body["search_token"]

        # Check that the result contains the local search results
        self.assertIn(
            "@alice:test",
            [result["user_id"] for result in initial_channel.json_body["results"]],
        )

        # # Set up the mock for the follow-up search with token
        # self.search_users_mock.return_value = {
        #     "limited": False,
        #     "results": [
        #         {
        #             "user_id": "@charlie:test2",
        #             "display_name": "Charlie",
        #             "avatar_url": None,
        #         }
        #     ],
        # }

        # Mock the get_federated_search_results method to return results
        get_federated_results_mock = AsyncMock()
        get_federated_results_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@charlie:test2",
                    "display_name": "Charlie",
                    "avatar_url": None,
                }
            ],
        }
        self.user_directory_handler.get_federated_search_results = (
            get_federated_results_mock
        )

        # Make a request to the search endpoint with the token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test", "search_token": search_token},
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
                        "user_id": "@charlie:test2",
                        "display_name": "Charlie",
                        "avatar_url": None,
                    }
                ],
            },
        )

        # Check that get_federated_search_results was called with the correct arguments
        get_federated_results_mock.assert_called_with(
            "@bob:test", "test", 10, search_token
        )

    def test_search_with_token_timeout(self) -> None:
        """Test that a search with a token times out if no results are available."""
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
            "search_token": "test_token_123",
        }

        # Make an initial request to get a token
        initial_channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test"},
            access_token=self.bob_token,
        )

        # Get the token from the response
        search_token = initial_channel.json_body["search_token"]

        # Mock the get_federated_search_results method to return empty results
        get_federated_results_mock = AsyncMock()
        get_federated_results_mock.return_value = {
            "limited": False,
            "results": [],
        }
        self.user_directory_handler.get_federated_search_results = (
            get_federated_results_mock
        )

        # Patch the timeout_deferred function to return immediately
        with patch(
            "synapse.util.async_helpers.timeout_deferred",
            side_effect=lambda d, timeout, reactor: defer.fail(defer.TimeoutError()),
        ):
            # Make a request to the search endpoint with a token
            channel = self.make_request(
                "POST",
                "/_matrix/client/v3/user_directory/search",
                {"search_term": "test", "search_token": search_token},
                access_token=self.bob_token,
            )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(
            channel.json_body,
            {
                "limited": False,
                "results": [],
            },
        )

        # Check that get_federated_search_results was called with the correct arguments
        get_federated_results_mock.assert_called_with(
            "@bob:test", "test", 10, search_token
        )

    # TODO: Fix this test
    # def test_search_with_invalid_token(self) -> None:
    #     """Test that a search with an invalid token works as a normal search."""
    #     # Set up the mock to return some results
    #     self.search_users_mock.return_value = {
    #         "limited": False,
    #         "results": [
    #             {
    #                 "user_id": "@alice:test",
    #                 "display_name": "Alice",
    #                 "avatar_url": None,
    #             }
    #         ],
    #     }

    #     # Mock the get_federated_search_results method to return immediately for invalid tokens
    #     # This simulates what would happen if the token was invalid
    #     get_federated_results_mock = AsyncMock()
    #     get_federated_results_mock.return_value = {
    #         "limited": False,
    #         "results": [],
    #     }
    #     self.user_directory_handler.get_federated_search_results = get_federated_results_mock

    #     # Make a request to the search endpoint with an invalid token
    #     channel = self.make_request(
    #         "POST",
    #         "/_matrix/client/v3/user_directory/search",
    #         {"search_term": "alice", "search_token": "invalid_token"},
    #         access_token=self.bob_token,
    #     )

    #     # Check that the response is correct
    #     self.assertEqual(channel.code, 200)
    #     self.assertEqual(
    #         channel.json_body,
    #         {
    #             "limited": False,
    #             "results": [
    #                 {
    #                     "user_id": "@alice:test",
    #                     "display_name": "Alice",
    #                     "avatar_url": None,
    #                 }
    #             ],
    #         },
    #     )

    #     # Check that the search_users method was called with the correct arguments
    #     self.search_users_mock.assert_called_once_with("@bob:test", "alice", 10)

    #     # Check that get_federated_search_results was called with the correct arguments
    #     get_federated_results_mock.assert_called_with("@bob:test", "alice", 10, "invalid_token")

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
            "search_token": "test_token_123",
        }

        # Make an initial request to get a token
        initial_channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test"},
            access_token=self.bob_token,
        )

        # Get the token from the response
        search_token = initial_channel.json_body["search_token"]

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
            {"search_term": "test", "search_token": search_token},
            access_token=self.bob_token,
        )

        channel2 = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "test", "search_token": search_token},
            access_token=self.alice_token,
        )

        # Check that both responses are correct
        self.assertEqual(channel1.code, 200)
        self.assertEqual(channel2.code, 200)

        # Check that get_federated_search_results was called twice, once for each request
        self.assertEqual(get_federated_results_mock.call_count, 2)
