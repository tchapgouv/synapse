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
import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from more_itertools.more import side_effect
from twisted.internet import defer
from twisted.test.proto_helpers import MemoryReactor

import synapse.rest.admin
from synapse.logging.context import run_in_background
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
    store_search_user_dir_mock: Any
    bob_token: Any
    alice_token: Any

    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        config = self.default_config()
        config["user_directory"] = {"enabled": True, "search_all_users": True}
        config["federation_domain_whitelist"] = ["test", "test2"]
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
        self.store_search_user_dir_mock = AsyncMock()
        self.user_directory_handler.store.search_user_dir = self.store_search_user_dir_mock
        # self.federation_client_user_directory_search_mock = AsyncMock()
        # self.user_directory_handler.federation_client.search_user_directory_across_federation = self.federation_client_user_directory_search_mock
        self.federation_client_user_directory_search_mock = AsyncMock()
        self.user_directory_handler.federation_client.user_directory_search = self.federation_client_user_directory_search_mock
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
        self.pending_search = None

    def test_search_users_on_first_call(self) -> None:
        """Test that a search without a search token works as expected."""
        # Set up the mock to return some results
        self.store_search_user_dir_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                {
                    "user_id": "@alice2:test",
                    "display_name": "Alice2",
                    "avatar_url": "mxc://test/alice2",
                }
            ]
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                }
            ],
        }

        # Make a request to the search endpoint without any search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], True)
        self.assertEqual(channel.json_body["search_token"], 1)
        self.assertEqual(channel.json_body["results"], [
                    {
                        "user_id": "@alice:test",
                        "display_name": "Alice",
                        "avatar_url": None,
                    },
                    {
                        "user_id": "@alice2:test",
                        "display_name": "Alice2",
                        "avatar_url": "mxc://test/alice2",
                    }
                ])

        # Check that the search_users method was called with the correct arguments
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 10, False)
        self.federation_client_user_directory_search_mock.assert_called_once_with("@bob:test", "test2", "alice", 10)

    def test_search_users_on_first_call_with_more_local_result(self) -> None:
        """Test that a search without a search token works as expected."""
        # Set up the mock to return some results
        self.store_search_user_dir_mock.return_value = {
            "limited": True,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                {
                    "user_id": "@alice2:test",
                    "display_name": "Alice2",
                    "avatar_url": "mxc://test/alice2",
                },
                {
                    "user_id": "@alice3:test",
                    "display_name": "Alice3",
                    "avatar_url": "mxc://test/alice3",
                },
                {
                    "user_id": "@alice4:test",
                    "display_name": "Alice4",
                    "avatar_url": "mxc://test/alice4",
                },
                {
                    "user_id": "@alice5:test",
                    "display_name": "Alice5",
                    "avatar_url": "mxc://test/alice5",
                },
                {
                    "user_id": "@alice6:test",
                    "display_name": "Alice6",
                    "avatar_url": "mxc://test/alice6",
                },
                {
                    "user_id": "@alice7:test",
                    "display_name": "Alice7",
                    "avatar_url": "mxc://test/alice7",
                },
                {
                    "user_id": "@alice8:test",
                    "display_name": "Alice8",
                    "avatar_url": "mxc://test/alice8",
                },
                {
                    "user_id": "@alice9:test",
                    "display_name": "Alice9",
                    "avatar_url": "mxc://test/alice9",
                },
                {
                    "user_id": "@alice10:test",
                    "display_name": "Alice10",
                    "avatar_url": "mxc://test/alice10",
                }
            ]
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                }
            ],
        }

        # Make a request to the search endpoint without any search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], True)
        self.assertEqual(channel.json_body["search_token"], 1)
        self.assertEqual(channel.json_body["results"], [
                    {
                        "user_id": "@alice:test",
                        "display_name": "Alice",
                        "avatar_url": None,
                    },
                    {
                        "user_id": "@alice2:test",
                        "display_name": "Alice2",
                        "avatar_url": "mxc://test/alice2",
                    },
                    {
                        "user_id": "@alice3:test",
                        "display_name": "Alice3",
                        "avatar_url": "mxc://test/alice3",
                    },
                    {
                        "user_id": "@alice4:test",
                        "display_name": "Alice4",
                        "avatar_url": "mxc://test/alice4",
                    },
                    {
                        "user_id": "@alice5:test",
                        "display_name": "Alice5",
                        "avatar_url": "mxc://test/alice5",
                    },
                    {
                        "user_id": "@alice6:test",
                        "display_name": "Alice6",
                        "avatar_url": "mxc://test/alice6",
                    },
                    {
                        "user_id": "@alice7:test",
                        "display_name": "Alice7",
                        "avatar_url": "mxc://test/alice7",
                    },
                    {
                        "user_id": "@alice8:test",
                        "display_name": "Alice8",
                        "avatar_url": "mxc://test/alice8",
                    },
                    {
                        "user_id": "@alice9:test",
                        "display_name": "Alice9",
                        "avatar_url": "mxc://test/alice9",
                    },
                    {
                        "user_id": "@alice10:test",
                        "display_name": "Alice10",
                        "avatar_url": "mxc://test/alice10",
                    }
                ])

        # Check that the search_users method was called with the correct arguments
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 10, False)
        self.federation_client_user_directory_search_mock.assert_called_once_with("@bob:test", "test2", "alice", 10)

    def test_search_users_on_second_call(self) -> None:
        """Test that a search with a search token works as expected."""
        # Set up the mock to return some results
        self.store_search_user_dir_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                {
                    "user_id": "@alice2:test",
                    "display_name": "Alice2",
                    "avatar_url": "mxc://test/alice2",
                }
            ]
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                }
            ],
        }

        # Make a request to the search endpoint without any search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        first_token = channel.json_body["search_token"]
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@john-marvelous2:test2",
                    "display_name": "John Marvelous2",
                    "avatar_url": "mxc://test2/john-marvelous2",
                }
            ],
        }

        # Make a request to the search endpoint with a search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "search_token": first_token},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], False)
        self.assertNotIn("search_token",channel.json_body)
        self.assertEqual(channel.json_body["results"], [
                    {
                        "user_id": "@john-marvelous:test2",
                        "display_name": "John Marvelous",
                        "avatar_url": "mxc://test2/john-marvelous",
                    }
                ],)

        # Check that the search_users method was called with the correct arguments
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 10, False)
        self.federation_client_user_directory_search_mock.assert_called_with("@bob:test", "test2", "alice", 10)
        self.assertEqual(self.federation_client_user_directory_search_mock.call_count,1)

    def test_search_users_on_second_call_with_more_local_result(self) -> None:
        """Test that a search with a search token works as expected."""
        # Set up the mock to return some results
        self.store_search_user_dir_mock.return_value = {
            "limited": True,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                {
                    "user_id": "@alice2:test",
                    "display_name": "Alice2",
                    "avatar_url": "mxc://test/alice2",
                },
                {
                    "user_id": "@alice3:test",
                    "display_name": "Alice3",
                    "avatar_url": "mxc://test/alice3",
                },
                {
                    "user_id": "@alice4:test",
                    "display_name": "Alice4",
                    "avatar_url": "mxc://test/alice4",
                },
                {
                    "user_id": "@alice5:test",
                    "display_name": "Alice5",
                    "avatar_url": "mxc://test/alice5",
                }
            ]
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                }
            ],
        }

        # Make a request to the search endpoint without any search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        first_token = channel.json_body["search_token"]
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@john-marvelous2:test2",
                    "display_name": "Alice Marvelous2",
                    "avatar_url": "mxc://test2/alice2-marvelous2",
                }
            ],
        }

        # Make a request to the search endpoint with a search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "search_token": first_token},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], False)
        self.assertNotIn("search_token",channel.json_body)
        self.assertEqual(channel.json_body["results"], [
                    {
                        "user_id": "@john-marvelous:test2",
                        "display_name": "John Marvelous",
                        "avatar_url": "mxc://test2/john-marvelous",
                    }
                ],)

        # Check that the search_users method was called with the correct arguments
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 10, False)
        self.federation_client_user_directory_search_mock.assert_called_with("@bob:test", "test2", "alice", 10)
        self.assertEqual(self.federation_client_user_directory_search_mock.call_count,1)

    def test_search_users_on_second_call_with_more_federated_result(self) -> None:
        """Test that a search with a search token works as expected."""
        # Set up the mock to return some results
        self.store_search_user_dir_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                {
                    "user_id": "@alice2:test",
                    "display_name": "Alice2",
                    "avatar_url": "mxc://test/alice2",
                }
            ]
        }
        self.federation_client_user_directory_search_mock.return_value = {
            "limited": True,
            "results": [
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                },
                {
                    "user_id": "@john-marvelous2:test2",
                    "display_name": "John Marvelous2",
                    "avatar_url": "mxc://test2/john-marvelous2",
                },
                {
                    "user_id": "@john-marvelous3:test2",
                    "display_name": "John Marvelous3",
                    "avatar_url": "mxc://test2/john-marvelous3",
                },
                {
                    "user_id": "@john-marvelous4:test2",
                    "display_name": "John Marvelous4",
                    "avatar_url": "mxc://test2/john-marvelous4",
                },
                {
                    "user_id": "@john-marvelous5:test2",
                    "display_name": "John Marvelous5",
                    "avatar_url": "mxc://test2/john-marvelous5",
                }
            ],
        }

        # Make a request to the search endpoint without any search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        first_token = channel.json_body["search_token"]

        # Make a request to the search endpoint with a search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "search_token": first_token},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], False)
        self.assertNotIn("search_token",channel.json_body)
        self.assertEqual(channel.json_body["results"], [
                    {
                        "user_id": "@alice:test",
                        "display_name": "Alice",
                        "avatar_url": None,
                    },
                    {
                        "user_id": "@alice2:test",
                        "display_name": "Alice2",
                        "avatar_url": "mxc://test/alice2",
                    },
                    {
                        "user_id": "@john-marvelous:test2",
                        "display_name": "John Marvelous",
                        "avatar_url": "mxc://test2/john-marvelous",
                    },
                    {
                        "user_id": "@john-marvelous2:test2",
                        "display_name": "John Marvelous2",
                        "avatar_url": "mxc://test2/john-marvelous2",
                    },
                    {
                        "user_id": "@john-marvelous3:test2",
                        "display_name": "John Marvelous3",
                        "avatar_url": "mxc://test2/john-marvelous3",
                    },
                    {
                        "user_id": "@john-marvelous4:test2",
                        "display_name": "John Marvelous4",
                        "avatar_url": "mxc://test2/john-marvelous4",
                    },
                    {
                        "user_id": "@john-marvelous5:test2",
                        "display_name": "John Marvelous5",
                        "avatar_url": "mxc://test2/john-marvelous5",
                    }
                ],)

        # Check that the search_users method was called with the correct arguments
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 10, False)
        self.federation_client_user_directory_search_mock.assert_called_with("@bob:test", "test2", "alice", 10)
        self.assertEqual(self.federation_client_user_directory_search_mock.call_count,1)

    def test_search_users_federation_arrives_later(self) -> None:
        """Test that the final search response have all federated search even if they are late"""

        local_results = {
            "limited": False,
            "results": [
                {"user_id": "@alice:test", "display_name": "Alice", "avatar_url": None},
                {"user_id": "@alice2:test", "display_name": "Alice2", "avatar_url": "mxc://test/alice2"},
            ]
        }
        federated_results = {
            "limited": True,
            "results": [

                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                },
                {
                    "user_id": "@john-marvelous2:test2",
                    "display_name": "John Marvelous2",
                    "avatar_url": "mxc://test2/john-marvelous2",
                },
                {
                    "user_id": "@john-marvelous3:test2",
                    "display_name": "John Marvelous3",
                    "avatar_url": "mxc://test2/john-marvelous3",
                },
                {
                    "user_id": "@john-marvelous4:test2",
                    "display_name": "John Marvelous4",
                    "avatar_url": "mxc://test2/john-marvelous4",
                },
                {
                    "user_id": "@john-marvelous5:test2",
                    "display_name": "John Marvelous5",
                    "avatar_url": "mxc://test2/john-marvelous5",
                }
            ],
        }

        self.store_search_user_dir_mock.return_value = local_results

        # Deferred that will simulate the asynchronous federated search
        federation_deferred: defer.Deferred = defer.Deferred()

        async def mock_federation(*args, **kwargs):
            return await federation_deferred

        self.federation_client_user_directory_search_mock.side_effect = mock_federation

        # FIRST REQUEST : should return local result
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice"},
            access_token=self.bob_token,
        )

        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["search_token"], 1)
        user_ids = [r["user_id"] for r in channel.json_body["results"]]
        self.assertIn("@alice:test", user_ids)
        self.assertNotIn("@john-marvelous:test2", user_ids)

        first_token = channel.json_body["search_token"]

        # SECOND REQUEST : with token should still return local result
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "search_token": first_token},
            access_token=self.bob_token,
        )

        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["search_token"], 2)
        user_ids = [r["user_id"] for r in channel.json_body["results"]]
        self.assertIn("@alice:test", user_ids)
        self.assertNotIn("@john-marvelous:test2", user_ids)

        second_token = channel.json_body["search_token"]

        # THIRD REQUEST : with token should still return local result
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "search_token": second_token},
            access_token=self.bob_token,
        )

        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["search_token"], 3)
        user_ids = [r["user_id"] for r in channel.json_body["results"]]
        self.assertIn("@alice:test", user_ids)
        self.assertNotIn("@john-marvelous:test2", user_ids)

        third_token = channel.json_body["search_token"]

        # Federated search has come back
        federation_deferred.callback(federated_results)
        self.pump()

        # FOURTH REQUEST : with token should return local + federated result
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "search_token": third_token},
            access_token=self.bob_token,
        )

        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], True)
        self.assertEqual(channel.json_body["search_token"], 4)
        user_ids = [r["user_id"] for r in channel.json_body["results"]]
        self.assertIn("@alice:test", user_ids)
        self.assertIn("@john-marvelous:test2", user_ids)
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["results"], local_results["results"] + federated_results["results"])
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 10, False)
        self.federation_client_user_directory_search_mock.assert_called_with("@bob:test", "test2", "alice", 10)
        self.assertEqual(self.federation_client_user_directory_search_mock.call_count, 1)

    def test_search_with_limit(self) -> None:
        """Test that a search with a limit works as expected."""
        # Set up the mock to return some results
        self.store_search_user_dir_mock.return_value = {
            "limited": False,
            "results": [
                {
                    "user_id": "@alice:test",
                    "display_name": "Alice",
                    "avatar_url": None,
                },
                {
                    "user_id": "@alice2:test",
                    "display_name": "Alice2",
                    "avatar_url": "mxc://test/alice2",
                }
            ]
        }

        self.federation_client_user_directory_search_mock.return_value = {
            "limited": True,
            "results": [
                {
                    "user_id": "@john-marvelous:test2",
                    "display_name": "John Marvelous",
                    "avatar_url": "mxc://test2/john-marvelous",
                },
                {
                    "user_id": "@john-marvelous2:test2",
                    "display_name": "John Marvelous2",
                    "avatar_url": "mxc://test2/john-marvelous2",
                },
                {
                    "user_id": "@john-marvelous3:test2",
                    "display_name": "John Marvelous3",
                    "avatar_url": "mxc://test2/john-marvelous3",
                },
                {
                    "user_id": "@john-marvelous4:test2",
                    "display_name": "John Marvelous4",
                    "avatar_url": "mxc://test2/john-marvelous4",
                },
                {
                    "user_id": "@john-marvelous5:test2",
                    "display_name": "John Marvelous5",
                    "avatar_url": "mxc://test2/john-marvelous5",
                }
            ],
        }

        # Make a request to the search endpoint without any search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "limit": 5},
            access_token=self.bob_token,
        )

        first_token = channel.json_body["search_token"]

        # Make a request to the search endpoint with a search token
        channel = self.make_request(
            "POST",
            "/_matrix/client/v3/user_directory/search",
            {"search_term": "alice", "limit": 5, "search_token": first_token},
            access_token=self.bob_token,
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body["limited"], True)
        self.assertEqual(channel.json_body["search_token"], 2)
        self.assertEqual(channel.json_body["results"], [
                    {
                        "user_id": "@alice:test",
                        "display_name": "Alice",
                        "avatar_url": None,
                    },
                    {
                        "user_id": "@alice2:test",
                        "display_name": "Alice2",
                        "avatar_url": "mxc://test/alice2",
                    },
                    {
                        "user_id": "@john-marvelous:test2",
                        "display_name": "John Marvelous",
                        "avatar_url": "mxc://test2/john-marvelous",
                    },
                    {
                        "user_id": "@john-marvelous2:test2",
                        "display_name": "John Marvelous2",
                        "avatar_url": "mxc://test2/john-marvelous2",
                    },
                    {
                        "user_id": "@john-marvelous3:test2",
                        "display_name": "John Marvelous3",
                        "avatar_url": "mxc://test2/john-marvelous3",
                    }
                ],)

        # Check that the search_users method was called with the correct arguments
        self.store_search_user_dir_mock.assert_called_once_with("@bob:test", "alice", 5, False)
        self.federation_client_user_directory_search_mock.assert_called_with("@bob:test", "test2", "alice", 5)
        self.assertEqual(self.federation_client_user_directory_search_mock.call_count,1)
