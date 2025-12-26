#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# Copyright 2023 Matrix.org Foundation C.I.C
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#
# Originally licensed under the Apache License, Version 2.0:
# <http://www.apache.org/licenses/LICENSE-2.0>.
#
#

from unittest.mock import AsyncMock, patch
from typing import Optional, Any

from twisted.test.proto_helpers import MemoryReactor

from synapse.api.errors import HttpResponseException
from synapse.rest import admin
from synapse.rest.client import login, register, room, user_directory
from synapse.server import HomeServer
from synapse.types import JsonDict
from synapse.util import Clock
from synapse.api.room_versions import RoomVersions
from synapse.federation.federation_client import FederationClient

from tests import unittest


class FederationClientUserDirectoryTestCase(unittest.FederatingHomeserverTestCase):
    """Tests for the federation client user directory search functionality."""

    servlets = [
        admin.register_servlets,
        login.register_servlets,
        register.register_servlets,
        room.register_servlets,
        user_directory.register_servlets,
    ]

    federation_client: Optional[FederationClient] = None
    transport_layer: Optional[Any] = None

    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        """Create a homeserver with federation enabled and user directory enabled."""
        config = self.default_config()
        config["user_directory"] = {
            "enabled": True,
            "search_all_users": True,
        }
        # Enable MSC4258
        config["experimental_features"] = {
            "msc4258_enabled": True,
        }

        return self.setup_test_homeserver(config=config)

    def prepare(self, reactor: MemoryReactor, clock: Clock, hs: HomeServer) -> None:
        """Set up the test."""
        super().prepare(reactor, clock, hs)
        self.federation_client = hs.get_federation_client()
        self.transport_layer = self.federation_client.transport_layer

    def test_user_directory_search(self) -> None:
        """Test that the federation client correctly handles user directory search requests."""
        # Mock the transport layer's user_directory_search method
        mock_results = {
            "limited": False,
            "results": [
                {
                    "user_id": "@user:other.example.com",
                    "display_name": "Test User",
                    "avatar_url": "mxc://example.com/avatar",
                }
            ],
        }
        self.transport_layer.user_directory_search = AsyncMock(return_value=mock_results)

        # Call the federation client method
        result = self.get_success(
            self.federation_client.user_directory_search(
                "other.example.com", "test", 10
            )
        )

        # Check that the result is correct
        self.assertEqual(result, mock_results)

        # Check that user_directory_search was called with the correct arguments
        self.transport_layer.user_directory_search.assert_called_once_with(
            "other.example.com", "test", 10
        )

    def test_user_directory_search_endpoint_not_found(self) -> None:
        """Test that the federation client handles 404 responses correctly."""
        # Mock the transport layer to raise a 404 error
        self.transport_layer.user_directory_search = AsyncMock(
            side_effect=HttpResponseException(
                404, "Not Found", b'{"errcode": "M_NOT_FOUND"}'
            )
        )

        # Call the federation client method
        result = self.get_success(
            self.federation_client.user_directory_search(
                "other.example.com", "test", 10
            )
        )

        # Check that the result is an empty result set
        self.assertEqual(result, {"limited": False, "results": []})

    def test_search_user_directory_across_federation(self) -> None:
        """Test that the federation client correctly handles searching across multiple servers."""
        # Mock the user_directory_search method to return different results for different servers
        async def mock_user_directory_search(
            destination: str, search_term: str, limit: int
        ) -> JsonDict:
            if destination == "server1.example.com":
                return {
                    "limited": False,
                    "results": [
                        {
                            "user_id": "@user1:server1.example.com",
                            "display_name": "User 1",
                            "avatar_url": "mxc://example.com/avatar1",
                        }
                    ],
                }
            elif destination == "server2.example.com":
                return {
                    "limited": False,
                    "results": [
                        {
                            "user_id": "@user2:server2.example.com",
                            "display_name": "User 2",
                            "avatar_url": "mxc://example.com/avatar2",
                        }
                    ],
                }
            else:
                return {"limited": False, "results": []}

        self.federation_client.user_directory_search = AsyncMock(
            side_effect=mock_user_directory_search
        )

        # Call the federation client method
        result = self.get_success(
            self.federation_client.search_user_directory_across_federation(
                ["server1.example.com", "server2.example.com"], "test", 10
            )
        )

        # Check that the result contains results from both servers
        self.assertEqual(
            result,
            {
                "limited": False,
                "results": [
                    {
                        "user_id": "@user1:server1.example.com",
                        "display_name": "User 1",
                        "avatar_url": "mxc://example.com/avatar1",
                    },
                    {
                        "user_id": "@user2:server2.example.com",
                        "display_name": "User 2",
                        "avatar_url": "mxc://example.com/avatar2",
                    },
                ],
            },
        )

    def test_search_user_directory_across_federation_with_limit(self) -> None:
        """Test that the federation client correctly applies limits when searching across multiple servers."""
        # Mock the user_directory_search method to return many results
        async def mock_user_directory_search(
            destination: str, search_term: str, limit: int
        ) -> JsonDict:
            return {
                "limited": False,
                "results": [
                    {
                        "user_id": f"@user{i}:{destination}",
                        "display_name": f"User {i}",
                        "avatar_url": f"mxc://example.com/avatar{i}",
                    }
                    for i in range(10)
                ],
            }

        self.federation_client.user_directory_search = AsyncMock(
            side_effect=mock_user_directory_search
        )

        # Call the federation client method with a limit of 5
        result = self.get_success(
            self.federation_client.search_user_directory_across_federation(
                ["server1.example.com", "server2.example.com"], "test", 5
            )
        )

        # Check that the result is limited to 5 users
        self.assertEqual(len(result["results"]), 5)
        self.assertTrue(result["limited"])

    def test_search_user_directory_across_federation_empty_destinations(self) -> None:
        """Test that the federation client handles empty destination lists correctly."""
        # Call the federation client method with an empty destination list
        result = self.get_success(
            self.federation_client.search_user_directory_across_federation(
                [], "test", 10
            )
        )

        # Check that the result is an empty result set
        self.assertEqual(result, {"limited": False, "results": []})

    def test_search_user_directory_across_federation_server_error(self) -> None:
        """Test that the federation client handles server errors correctly."""
        # Mock the _try_destination_list method to return None (indicating all servers failed)
        self.federation_client.user_directory_search = AsyncMock(
            side_effect=HttpResponseException(
                500, "Internal Server Error", b"{}"
            )
        )

        # Call the federation client method
        result = self.get_success(
            self.federation_client.search_user_directory_across_federation(
                ["server1.example.com", "server2.example.com"], "test", 10
            )
        )

        # Check that the result is an empty result set
        self.assertEqual(result, {"limited": False, "results": []})

    def test_user_directory_search_with_token(self) -> None:
        """Test that the user directory search endpoint correctly handles search tokens."""
        # Create a user
        user_id = self.register_user("user", "password")
        access_token = self.login("user", "password")

        # Mock the user_directory_handler's search_users method
        with patch.object(
            self.hs.get_user_directory_handler(),
            "search_users",
            new=AsyncMock(
                return_value={
                    "limited": True,
                    "results": [
                        {
                            "user_id": "@user:test",
                            "display_name": "Test User",
                            "avatar_url": "mxc://example.com/avatar",
                        }
                    ],
                    "search_token": "test_token_123",
                }
            ),
        ):
            # Make a search request
            channel = self.make_request(
                "POST",
                "/_matrix/client/v3/user_directory/search",
                {"search_term": "test", "limit": 10},
                access_token=access_token,
            )

            # Check that the response contains a search token
            self.assertEqual(channel.code, 200)
            self.assertEqual(channel.json_body.get("search_token"), "test_token_123")
            self.assertTrue(channel.json_body.get("limited"))

    def test_user_directory_search_with_token_federated_results(self) -> None:
        """Test that the user directory search endpoint correctly handles federated results with search tokens."""
        # Create a user
        user_id = self.register_user("user", "password")
        access_token = self.login("user", "password")

        # Mock the user_directory_handler's get_federated_search_results method
        with patch.object(
            self.hs.get_user_directory_handler(),
            "get_federated_search_results",
            new=AsyncMock(
                return_value={
                    "limited": False,
                    "results": [
                        {
                            "user_id": "@user:other.example.com",
                            "display_name": "Remote User",
                            "avatar_url": "mxc://example.com/remote_avatar",
                        }
                    ],
                }
            ),
        ):
            # Make a search request with a token
            channel = self.make_request(
                "POST",
                "/_matrix/client/v3/user_directory/search",
                {"search_term": "test", "limit": 10, "search_token": "test_token_123"},
                access_token=access_token,
            )

            # Check that the response contains federated results
            self.assertEqual(channel.code, 200)
            self.assertEqual(len(channel.json_body.get("results", [])), 1)
            self.assertEqual(
                channel.json_body.get("results", [])[0].get("user_id"),
                "@user:other.example.com",
            )

    def test_user_directory_search_with_token_no_results(self) -> None:
        """Test that the user directory search endpoint correctly handles no federated results."""
        # Create a user
        user_id = self.register_user("user", "password")
        access_token = self.login("user", "password")

        # Mock the user_directory_handler's get_federated_search_results method
        with patch.object(
            self.hs.get_user_directory_handler(),
            "get_federated_search_results",
            new=AsyncMock(return_value={"limited": False, "results": []}),
        ):
            # Make a search request with a token
            channel = self.make_request(
                "POST",
                "/_matrix/client/v3/user_directory/search",
                {"search_term": "test", "limit": 10, "search_token": "test_token_123"},
                access_token=access_token,
            )

            # Check that the response is empty
            self.assertEqual(channel.code, 200)
            self.assertEqual(len(channel.json_body.get("results", [])), 0)
            self.assertFalse(channel.json_body.get("limited", False)) 