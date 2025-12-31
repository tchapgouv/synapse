#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# Copyright 2017 Vector Creations Ltd
# Copyright (C) 2023 New Vector, Ltd
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
# [This file includes modifications made by New Vector Limited]
#
#

import logging
import time
from typing import TYPE_CHECKING, Tuple

from synapse.api.errors import SynapseError
from synapse.http.server import HttpServer
from synapse.http.servlet import RestServlet, parse_json_object_from_request
from synapse.http.site import SynapseRequest
from synapse.types import JsonMapping
from synapse.util.async_helpers import run_in_background

from ._base import client_patterns

if TYPE_CHECKING:
    from synapse.server import HomeServer

logger = logging.getLogger(__name__)


class UserDirectorySearchRestServlet(RestServlet):
    PATTERNS = client_patterns("/user_directory/search$")
    CATEGORY = "User directory search requests"

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self.hs = hs
        self.auth = hs.get_auth()
        self.user_directory_handler = hs.get_user_directory_handler()
        self.clock = hs.get_clock()
        self.is_mine_server_name = hs.is_mine_server_name

    # TODO: add search_scope: local, restricted, remote
    async def on_POST(self, request: SynapseRequest) -> Tuple[int, JsonMapping]:
        """Searches for users in directory, including federated results

        Request:
            {
                "search_term": "search query",
                "limit": 10,
                "search_token": "a1d29g4f73"  # Optional, for retrieving more results
            }

        Returns:
            dict of the form::

                {
                    "limited": <bool>,  # whether there were more results or not
                    "results": [  # Ordered by best match first
                        {
                            "user_id": <user_id>,
                            "display_name": <display_name>,
                            "avatar_url": <avatar_url>,
                            "m.user_directory.visibility": <visibility>
                        }
                    ],
                    "search_token": <token for retrieving more results>
                }
        """
        requester = await self.auth.get_user_by_req(request, allow_guest=False)
        user_id = requester.user.to_string()

        if not self.hs.config.userdirectory.user_directory_search_enabled:
            return 200, {"limited": False, "results": []}

        body = parse_json_object_from_request(request)

        limit = int(body.get("limit", 10))
        limit = max(min(limit, 50), 0)

        try:
            search_term = body["search_term"]
        except Exception:
            raise SynapseError(400, "`search_term` is required field")

        # Check if we have a search token
        search_token = body.get("search_token")

        # If we have a search token, this is a request for more results
        if search_token:
            # Wait for federated results
            start_time = time.time()
            timeout = 30.0  # 30 seconds timeout

            # Try to get federated results from cache
            federated_results = (
                await self.user_directory_handler.get_federated_search_results(
                    user_id, search_term, limit, search_token
                )
            )

            # If we got results or timed out, return them
            if (
                federated_results.get("results")
                or (time.time() - start_time) >= timeout
            ):
                return 200, federated_results

            # If we didn't get results yet, wait a bit and try again
            # This simulates long-polling
            await self.clock.sleep(1.0)

            # Try again to get results from cache
            federated_results = (
                await self.user_directory_handler.get_federated_search_results(
                    user_id, search_term, limit, search_token
                )
            )

            return 200, federated_results

        # Get local results first
        local_results = await self.user_directory_handler.search_users(
            user_id, search_term, limit
        )

        # Start the federated search in the background
        # This will be picked up by the next request with the search_token
        if local_results.get("search_token"):
            search_token = local_results["search_token"]

            # Start the federated search in the background
            # We don't await this, it will run in the background
            run_in_background(
                self.user_directory_handler.get_federated_search_results,
                user_id,
                search_term,
                limit,
                search_token,
            )

        return 200, local_results


def register_servlets(hs: "HomeServer", http_server: HttpServer) -> None:
    UserDirectorySearchRestServlet(hs).register(http_server)
