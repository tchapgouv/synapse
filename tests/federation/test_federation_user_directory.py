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
from twisted.test.proto_helpers import MemoryReactor

from synapse.rest import admin
from synapse.rest.client import login, register, room, user_directory
from synapse.server import HomeServer
from synapse.util import Clock

from tests import unittest
from tests.unittest import override_config

import logging
logger = logging.getLogger(__name__)

class FederationUserDirectoryServletTestCase(unittest.FederatingHomeserverTestCase):
    """Tests for the federation user directory search servlet."""

    servlets = [
        admin.register_servlets,
        login.register_servlets,
        register.register_servlets,
        room.register_servlets,
        user_directory.register_servlets,
    ]
    
    # Initialize instance variables to avoid linter errors
    federation_server = None
    user_directory_handler = None

    def default_config(self):
        config = super().default_config()
        config["user_directory"] = {
            "enabled": True,
            "search_all_users": True,
        }
        # This is the server config option, not the federation config option
        config["allow_profile_lookup_over_federation"] = True
        return config

    def prepare(self, reactor: MemoryReactor, clock: Clock, hs: HomeServer) -> None:
        """Set up the test."""
        super().prepare(reactor, clock, hs)
        self.federation_server = hs.get_federation_server()
        self.user_directory_handler = hs.get_user_directory_handler()

        self.register_user("user", "password")

    @override_config({"experimental_features": {"msc4258_enabled": True}})
    def test_federation_user_directory_search_servlet(self) -> None:
        """Test that the federation user directory search servlet works correctly."""
        # Make a request to the servlet
        channel = self.make_signed_federation_request(
            "POST",
            "/_matrix/federation/unstable/org.matrix.msc4258/user_directory/search",
            content={"search_term": "test", "limit": 10},
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body.get("limited", None), False)
        results = channel.json_body.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].get("user_id"), "@user:test")

    @override_config({"experimental_features": {"msc4258_enabled": True}})
    def test_federation_user_directory_search_servlet_invalid_request(self) -> None:
        """Test that the federation user directory search servlet rejects invalid requests."""
        # Make a request with missing search_term
        channel = self.make_signed_federation_request(
            "POST",
            "/_matrix/federation/unstable/org.matrix.msc4258/user_directory/search",
            content={"limit": 10},
        )

        # Check that the response is an error
        self.assertEqual(channel.code, 400)
        self.assertEqual(channel.json_body["errcode"], "M_BAD_JSON") 

    @override_config({"experimental_features": {"msc4258_enabled": True}})
    def test_federation_user_directory_search_servlet_no_results(self) -> None:
        """Test that the federation user directory search servlet works correctly."""
        # Make a request to the servlet
        channel = self.make_signed_federation_request(
            "POST",
            "/_matrix/federation/unstable/org.matrix.msc4258/user_directory/search",
            content={"search_term": "nonexistent", "limit": 10},
        )

        # Check that the response is correct
        self.assertEqual(channel.code, 200)
        self.assertEqual(channel.json_body.get("limited", None), False)
        results = channel.json_body.get("results", [])
        self.assertEqual(len(results), 0)

    def test_federation_user_directory_search_servlet_msc4258_disabled(self) -> None:
        """Test that the federation user directory search servlet rejects requests when MSC4258 is disabled."""
        logger.error(f"msc4258_enabled: {self.hs.config.experimental.msc4258_enabled}")
        # Make a request to the servlet
        channel = self.make_signed_federation_request(
            "POST",
            "/_matrix/federation/unstable/org.matrix.msc4258/user_directory/search",
            content={"search_term": "test", "limit": 10},
        )

        # Check that the response is an error
        self.assertEqual(channel.code, 404)
