#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# Copyright 2014-2016 OpenMarket Ltd
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
from typing import Any, Awaitable, Callable
from unittest.mock import AsyncMock, Mock, patch

from parameterized import parameterized

from twisted.internet.testing import MemoryReactor

import synapse.rest.client.login
import synapse.rest.client.room
import synapse.types
from synapse.api.errors import AuthError, SynapseError
from synapse.handlers.profile import UPDATE_JOIN_STATES_ACTION_NAME
from synapse.rest import admin
from synapse.server import HomeServer
from synapse.types import JsonDict, TaskStatus, UserID
from synapse.util.clock import Clock
from synapse.util.task_scheduler import TaskScheduler

from tests import unittest


class ProfileTestCase(unittest.HomeserverTestCase):
    """Tests profile management."""

    servlets = [admin.register_servlets]

    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        self.mock_federation = AsyncMock()
        self.mock_registry = Mock()

        self.query_handlers: dict[str, Callable[[dict], Awaitable[JsonDict]]] = {}

        def register_query_handler(
            query_type: str, handler: Callable[[dict], Awaitable[JsonDict]]
        ) -> None:
            self.query_handlers[query_type] = handler

        self.mock_registry.register_query_handler = register_query_handler

        hs = self.setup_test_homeserver(
            federation_client=self.mock_federation,
            federation_server=Mock(),
            federation_registry=self.mock_registry,
        )
        return hs

    def prepare(self, reactor: MemoryReactor, clock: Clock, hs: HomeServer) -> None:
        self.store = hs.get_datastores().main

        self.frank = UserID.from_string("@1234abcd:test")
        self.bob = UserID.from_string("@4567:test")
        self.alice = UserID.from_string("@alice:remote")

        self.register_user(self.frank.localpart, "frankpassword")

        self.handler = hs.get_profile_handler()

    def test_get_my_name(self) -> None:
        self.get_success(self.store.set_profile_displayname(self.frank, "Frank"))

        displayname = self.get_success(self.handler.get_displayname(self.frank))

        self.assertEqual("Frank", displayname)

    def test_set_my_name(self) -> None:
        self.get_success(
            self.handler.set_displayname(
                self.frank, synapse.types.create_requester(self.frank), "Frank Jr."
            )
        )

        self.assertEqual(
            (self.get_success(self.store.get_profile_displayname(self.frank))),
            "Frank Jr.",
        )

        # Set displayname again
        self.get_success(
            self.handler.set_displayname(
                self.frank, synapse.types.create_requester(self.frank), "Frank"
            )
        )

        self.assertEqual(
            (self.get_success(self.store.get_profile_displayname(self.frank))),
            "Frank",
        )

        # Set displayname to an empty string
        self.get_success(
            self.handler.set_displayname(
                self.frank, synapse.types.create_requester(self.frank), ""
            )
        )

        self.assertIsNone(
            self.get_success(self.store.get_profile_displayname(self.frank))
        )

    def test_set_my_name_if_disabled(self) -> None:
        self.hs.config.registration.enable_set_displayname = False

        # Setting displayname for the first time is allowed
        self.get_success(self.store.set_profile_displayname(self.frank, "Frank"))

        self.assertEqual(
            (self.get_success(self.store.get_profile_displayname(self.frank))),
            "Frank",
        )

        # Setting displayname a second time is forbidden
        self.get_failure(
            self.handler.set_displayname(
                self.frank, synapse.types.create_requester(self.frank), "Frank Jr."
            ),
            SynapseError,
        )

    def test_set_my_name_noauth(self) -> None:
        self.get_failure(
            self.handler.set_displayname(
                self.frank, synapse.types.create_requester(self.bob), "Frank Jr."
            ),
            AuthError,
        )

    def test_get_other_name(self) -> None:
        self.mock_federation.make_query.return_value = {"displayname": "Alice"}

        displayname = self.get_success(self.handler.get_displayname(self.alice))

        self.assertEqual(displayname, "Alice")
        self.mock_federation.make_query.assert_called_with(
            destination="remote",
            query_type="profile",
            args={"user_id": "@alice:remote", "field": "displayname"},
            ignore_backoff=True,
        )

    def test_incoming_fed_query(self) -> None:
        self.get_success(
            self.store.create_profile(UserID.from_string("@caroline:test"))
        )
        self.get_success(
            self.store.set_profile_displayname(
                UserID.from_string("@caroline:test"), "Caroline"
            )
        )

        response = self.get_success(
            self.query_handlers["profile"](
                {
                    "user_id": "@caroline:test",
                    "field": "displayname",
                    "origin": "servername.tld",
                }
            )
        )

        self.assertEqual({"displayname": "Caroline"}, response)

    def test_get_my_avatar(self) -> None:
        self.get_success(
            self.store.set_profile_avatar_url(self.frank, "http://my.server/me.png")
        )
        avatar_url = self.get_success(self.handler.get_avatar_url(self.frank))

        self.assertEqual("http://my.server/me.png", avatar_url)

    def test_get_profile_empty_displayname(self) -> None:
        self.get_success(self.store.set_profile_displayname(self.frank, None))
        self.get_success(
            self.store.set_profile_avatar_url(self.frank, "http://my.server/me.png")
        )

        profile = self.get_success(self.handler.get_profile(self.frank.to_string()))

        self.assertEqual("http://my.server/me.png", profile["avatar_url"])

    def test_set_my_avatar(self) -> None:
        self.get_success(
            self.handler.set_avatar_url(
                self.frank,
                synapse.types.create_requester(self.frank),
                "http://my.server/pic.gif",
            )
        )

        self.assertEqual(
            (self.get_success(self.store.get_profile_avatar_url(self.frank))),
            "http://my.server/pic.gif",
        )

        # Set avatar again
        self.get_success(
            self.handler.set_avatar_url(
                self.frank,
                synapse.types.create_requester(self.frank),
                "http://my.server/me.png",
            )
        )

        self.assertEqual(
            (self.get_success(self.store.get_profile_avatar_url(self.frank))),
            "http://my.server/me.png",
        )

        # Set avatar to an empty string
        self.get_success(
            self.handler.set_avatar_url(
                self.frank,
                synapse.types.create_requester(self.frank),
                "",
            )
        )

        self.assertIsNone(
            (self.get_success(self.store.get_profile_avatar_url(self.frank))),
        )

    def test_set_my_avatar_if_disabled(self) -> None:
        self.hs.config.registration.enable_set_avatar_url = False

        # Setting displayname for the first time is allowed
        self.get_success(
            self.store.set_profile_avatar_url(self.frank, "http://my.server/me.png")
        )

        self.assertEqual(
            (self.get_success(self.store.get_profile_avatar_url(self.frank))),
            "http://my.server/me.png",
        )

        # Set avatar a second time is forbidden
        self.get_failure(
            self.handler.set_avatar_url(
                self.frank,
                synapse.types.create_requester(self.frank),
                "http://my.server/pic.gif",
            ),
            SynapseError,
        )

    def test_avatar_constraints_no_config(self) -> None:
        """Tests that the method to check an avatar against configured constraints skips
        all of its check if no constraint is configured.
        """
        # The first check that's done by this method is whether the file exists; if we
        # don't get an error on a non-existing file then it means all of the checks were
        # successfully skipped.
        res = self.get_success(
            self.handler.check_avatar_size_and_mime_type("mxc://test/unknown_file")
        )
        self.assertTrue(res)

    @unittest.override_config({"max_avatar_size": 50})
    def test_avatar_constraints_allow_empty_avatar_url(self) -> None:
        """An empty avatar is always permitted."""
        res = self.get_success(self.handler.check_avatar_size_and_mime_type(""))
        self.assertTrue(res)

    @unittest.override_config({"max_avatar_size": 50})
    def test_avatar_constraints_missing(self) -> None:
        """Tests that an avatar isn't allowed if the file at the given MXC URI couldn't
        be found.
        """
        res = self.get_success(
            self.handler.check_avatar_size_and_mime_type("mxc://test/unknown_file")
        )
        self.assertFalse(res)

    @unittest.override_config({"max_avatar_size": 50})
    def test_avatar_constraints_file_size(self) -> None:
        """Tests that a file that's above the allowed file size is forbidden but one
        that's below it is allowed.
        """
        self._setup_local_files(
            {
                "small": {"size": 40},
                "big": {"size": 60},
            }
        )

        res = self.get_success(
            self.handler.check_avatar_size_and_mime_type("mxc://test/small")
        )
        self.assertTrue(res)

        res = self.get_success(
            self.handler.check_avatar_size_and_mime_type("mxc://test/big")
        )
        self.assertFalse(res)

    @unittest.override_config({"allowed_avatar_mimetypes": ["image/png"]})
    def test_avatar_constraint_mime_type(self) -> None:
        """Tests that a file with an unauthorised MIME type is forbidden but one with
        an authorised content type is allowed.
        """
        self._setup_local_files(
            {
                "good": {"mimetype": "image/png"},
                "bad": {"mimetype": "application/octet-stream"},
            }
        )

        res = self.get_success(
            self.handler.check_avatar_size_and_mime_type("mxc://test/good")
        )
        self.assertTrue(res)

        res = self.get_success(
            self.handler.check_avatar_size_and_mime_type("mxc://test/bad")
        )
        self.assertFalse(res)

    @unittest.override_config(
        {"server_name": "test:8888", "allowed_avatar_mimetypes": ["image/png"]}
    )
    def test_avatar_constraint_on_local_server_with_port(self) -> None:
        """Test that avatar metadata is correctly fetched when the media is on a local
        server and the server has an explicit port.

        (This was previously a bug)
        """
        local_server_name = self.hs.config.server.server_name
        media_id = "local"
        local_mxc = f"mxc://{local_server_name}/{media_id}"

        # mock up the existence of the avatar file
        self._setup_local_files({media_id: {"mimetype": "image/png"}})

        # and now check that check_avatar_size_and_mime_type is happy
        self.assertTrue(
            self.get_success(self.handler.check_avatar_size_and_mime_type(local_mxc))
        )

    @parameterized.expand([("remote",), ("remote:1234",)])
    @unittest.override_config({"allowed_avatar_mimetypes": ["image/png"]})
    def test_check_avatar_on_remote_server(self, remote_server_name: str) -> None:
        """Test that avatar metadata is correctly fetched from a remote server"""
        media_id = "remote"
        remote_mxc = f"mxc://{remote_server_name}/{media_id}"

        # if the media is remote, check_avatar_size_and_mime_type just checks the
        # media cache, so we don't need to instantiate a real remote server. It is
        # sufficient to poke an entry into the db.
        self.get_success(
            self.hs.get_datastores().main.store_cached_remote_media(
                media_id=media_id,
                media_type="image/png",
                media_length=50,
                origin=remote_server_name,
                time_now_ms=self.clock.time_msec(),
                upload_name=None,
                filesystem_id="xyz",
                sha256="abcdefg12345",
            )
        )

        self.assertTrue(
            self.get_success(self.handler.check_avatar_size_and_mime_type(remote_mxc))
        )

    def _setup_local_files(self, names_and_props: dict[str, dict[str, Any]]) -> None:
        """Stores metadata about files in the database.

        Args:
            names_and_props: A dictionary with one entry per file, with the key being the
                file's name, and the value being a dictionary of properties. Supported
                properties are "mimetype" (for the file's type) and "size" (for the
                file's size).
        """
        store = self.hs.get_datastores().main

        for name, props in names_and_props.items():
            self.get_success(
                store.store_local_media(
                    media_id=name,
                    media_type=props.get("mimetype", "image/png"),
                    time_now_ms=self.clock.time_msec(),
                    upload_name=None,
                    media_length=props.get("size", 50),
                    user_id=UserID.from_string("@rin:test"),
                )
            )


class UpdateJoinStatesTestCase(unittest.HomeserverTestCase):
    """Tests for backgrounded membership updates when changing profile."""

    servlets = [
        admin.register_servlets,
        synapse.rest.client.login.register_servlets,
        synapse.rest.client.room.register_servlets,
    ]

    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        self.mock_federation = AsyncMock()
        self.mock_registry = Mock()

        self.query_handlers: dict[str, Callable[[dict], Awaitable[JsonDict]]] = {}

        def register_query_handler(
            query_type: str, handler: Callable[[dict], Awaitable[JsonDict]]
        ) -> None:
            self.query_handlers[query_type] = handler

        self.mock_registry.register_query_handler = register_query_handler

        hs = self.setup_test_homeserver(
            federation_client=self.mock_federation,
            federation_server=Mock(),
            federation_registry=self.mock_registry,
        )
        return hs

    def prepare(self, reactor: MemoryReactor, clock: Clock, hs: HomeServer) -> None:
        self.store = hs.get_datastores().main
        self.handler = hs.get_profile_handler()
        self.task_scheduler = hs.get_task_scheduler()

        # Create a user and log them in
        self.user_id = self.register_user("alice", "password")
        self.user_token = self.login("alice", "password")
        self.user = UserID.from_string(self.user_id)

    def test_set_displayname_schedules_task(self) -> None:
        """Test that setting displayname schedules an update_join_states task."""
        # Set the displayname
        self.get_success(
            self.handler.set_displayname(
                self.user,
                synapse.types.create_requester(self.user),
                "New Display Name",
            )
        )

        # Check that a task was scheduled
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        self.assertEqual(len(tasks), 1)
        self.assertIn(tasks[0].status, [TaskStatus.SCHEDULED, TaskStatus.ACTIVE, TaskStatus.COMPLETE])
        self.assertEqual(tasks[0].params.get("requester_authenticated_entity"), self.user_id)

    def test_set_avatar_schedules_task(self) -> None:
        """Test that setting avatar URL schedules an update_join_states task."""
        # Set the avatar URL
        self.get_success(
            self.handler.set_avatar_url(
                self.user,
                synapse.types.create_requester(self.user),
                "http://my.server/avatar.png",
            )
        )

        # Check that a task was scheduled
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        self.assertEqual(len(tasks), 1)
        self.assertIn(tasks[0].status, [TaskStatus.SCHEDULED, TaskStatus.ACTIVE, TaskStatus.COMPLETE])

    def test_set_displayname_no_propagate_does_not_schedule_task(self) -> None:
        """Test that setting displayname with propagate=False does not schedule a task."""
        # Set the displayname without propagation
        self.get_success(
            self.handler.set_displayname(
                self.user,
                synapse.types.create_requester(self.user),
                "New Display Name",
                propagate=False,
            )
        )

        # Check that no task was scheduled
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        self.assertEqual(len(tasks), 0)

    def test_set_avatar_no_propagate_does_not_schedule_task(self) -> None:
        """Test that setting avatar URL with propagate=False does not schedule a task."""
        # Set the avatar URL without propagation
        self.get_success(
            self.handler.set_avatar_url(
                self.user,
                synapse.types.create_requester(self.user),
                "http://my.server/avatar.png",
                propagate=False,
            )
        )

        # Check that no task was scheduled
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        self.assertEqual(len(tasks), 0)

    def test_rapid_profile_changes_cancel_pending_tasks(self) -> None:
        """Test that rapid profile changes cancel pending tasks before scheduling new ones."""
        # We need to prevent the task from completing immediately so we can see the cancellation
        # Pause the task scheduler so tasks don't run
        with patch.object(
            self.handler, "_update_join_states_task", new_callable=AsyncMock
        ) as mock_task:
            # Make the mock task return COMPLETE status
            mock_task.return_value = (TaskStatus.COMPLETE, None, None)

            # Set displayname multiple times rapidly
            self.get_success(
                self.handler.set_displayname(
                    self.user,
                    synapse.types.create_requester(self.user),
                    "Name 1",
                )
            )

            first_tasks = self.get_success(
                self.task_scheduler.get_tasks(
                    actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                    resource_id=self.user_id,
                    statuses=[TaskStatus.SCHEDULED, TaskStatus.ACTIVE],
                )
            )

            # Change displayname again - this should cancel the previous task
            self.get_success(
                self.handler.set_displayname(
                    self.user,
                    synapse.types.create_requester(self.user),
                    "Name 2",
                )
            )

            # The first task should be cancelled
            if first_tasks:
                first_task = self.get_success(
                    self.task_scheduler.get_task(first_tasks[0].id)
                )
                if first_task:
                    self.assertEqual(first_task.status, TaskStatus.CANCELLED)

            # There should be a new scheduled/active task
            current_tasks = self.get_success(
                self.task_scheduler.get_tasks(
                    actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                    resource_id=self.user_id,
                    statuses=[TaskStatus.SCHEDULED, TaskStatus.ACTIVE],
                )
            )
            self.assertEqual(len(current_tasks), 1)

    def test_update_join_states_task_updates_memberships(self) -> None:
        """Test that the update_join_states task updates membership events in rooms."""
        # Create a room and join it
        room_id = self.helper.create_room_as(self.user_id, tok=self.user_token)

        # Set the displayname
        self.get_success(
            self.handler.set_displayname(
                self.user,
                synapse.types.create_requester(self.user),
                "Updated Name",
            )
        )

        # Wait for the task to complete
        self.reactor.advance(TaskScheduler.SCHEDULE_INTERVAL.as_secs())

        # Check that the membership event was updated
        # Get the current state of the room
        state = self.get_success(
            self.store.get_current_state_for_key(
                room_id, "m.room.member", self.user_id
            )
        )
        self.assertIsNotNone(state)
        self.assertEqual(state.content.get("displayname"), "Updated Name")

    def test_update_join_states_task_updates_multiple_rooms(self) -> None:
        """Test that the update_join_states task updates membership in all rooms."""
        # Create multiple rooms
        room_id_1 = self.helper.create_room_as(self.user_id, tok=self.user_token)
        room_id_2 = self.helper.create_room_as(self.user_id, tok=self.user_token)
        room_id_3 = self.helper.create_room_as(self.user_id, tok=self.user_token)

        # Set the displayname
        self.get_success(
            self.handler.set_displayname(
                self.user,
                synapse.types.create_requester(self.user),
                "Multi Room Name",
            )
        )

        # Wait for the task to complete
        self.reactor.advance(TaskScheduler.SCHEDULE_INTERVAL.as_secs())

        # Check all rooms have updated membership
        for room_id in [room_id_1, room_id_2, room_id_3]:
            state = self.get_success(
                self.store.get_current_state_for_key(
                    room_id, "m.room.member", self.user_id
                )
            )
            self.assertIsNotNone(state)
            self.assertEqual(state.content.get("displayname"), "Multi Room Name")

    def test_update_join_states_task_resumes_from_last_room(self) -> None:
        """Test that the update_join_states task can resume from the last processed room."""
        # Create multiple rooms
        room_ids = []
        for _ in range(3):
            room_id = self.helper.create_room_as(self.user_id, tok=self.user_token)
            room_ids.append(room_id)

        # Sort room IDs to match how the task processes them
        room_ids = sorted(room_ids)

        # Create a mock task with a last_room_id that should skip the first room
        mock_task = Mock()
        mock_task.resource_id = self.user_id
        mock_task.params = {"requester_authenticated_entity": self.user_id}
        mock_task.result = {"last_room_id": room_ids[0]}  # Skip first room
        mock_task.id = "test_task_id"

        # Track which rooms get updated
        updated_rooms: list[str] = []
        original_update_membership = self.hs.get_room_member_handler().update_membership

        async def tracking_update_membership(
            requester: Any,
            target: Any,
            room_id: str,
            action: str,
            **kwargs: Any,
        ) -> Any:
            updated_rooms.append(room_id)
            return await original_update_membership(
                requester, target, room_id, action, **kwargs
            )

        with patch.object(
            self.hs.get_room_member_handler(),
            "update_membership",
            side_effect=tracking_update_membership,
        ):
            # Run the task directly
            self.get_success(self.handler._update_join_states_task(mock_task))

        # Only the rooms after last_room_id should be updated
        expected_rooms = [r for r in room_ids if r > room_ids[0]]
        self.assertEqual(sorted(updated_rooms), sorted(expected_rooms))

    def test_shadow_banned_user_does_not_update_rooms(self) -> None:
        """Test that shadow banned users don't get their room memberships updated."""
        # Create a room
        room_id = self.helper.create_room_as(self.user_id, tok=self.user_token)

        # Get initial membership state
        initial_state = self.get_success(
            self.store.get_current_state_for_key(
                room_id, "m.room.member", self.user_id
            )
        )

        # Create a shadow banned requester
        shadow_banned_requester = synapse.types.create_requester(
            self.user, shadow_banned=True
        )

        # Set displayname with shadow banned requester
        self.get_success(
            self.handler.set_displayname(
                self.user,
                shadow_banned_requester,
                "Shadow Banned Name",
            )
        )

        # Wait some time for potential task execution
        self.reactor.advance(TaskScheduler.SCHEDULE_INTERVAL.as_secs() + 15)

        # The profile should be updated in the database
        displayname = self.get_success(self.store.get_profile_displayname(self.user))
        self.assertEqual(displayname, "Shadow Banned Name")

        # But no task should have been scheduled (shadow banned users sleep randomly instead)
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        self.assertEqual(len(tasks), 0)

    def test_update_join_states_task_handles_room_errors_gracefully(self) -> None:
        """Test that the task continues even if updating one room fails."""
        # Create multiple rooms
        room_id_1 = self.helper.create_room_as(self.user_id, tok=self.user_token)
        room_id_2 = self.helper.create_room_as(self.user_id, tok=self.user_token)

        room_ids = sorted([room_id_1, room_id_2])
        call_count = 0

        original_update_membership = self.hs.get_room_member_handler().update_membership

        async def failing_update_membership(
            requester: Any,
            target: Any,
            room_id: str,
            action: str,
            **kwargs: Any,
        ) -> Any:
            nonlocal call_count
            call_count += 1
            # Fail on the first room
            if room_id == room_ids[0]:
                raise Exception("Simulated failure")
            return await original_update_membership(
                requester, target, room_id, action, **kwargs
            )

        with patch.object(
            self.hs.get_room_member_handler(),
            "update_membership",
            side_effect=failing_update_membership,
        ):
            # Set the displayname
            self.get_success(
                self.handler.set_displayname(
                    self.user,
                    synapse.types.create_requester(self.user),
                    "Error Test Name",
                )
            )

            # Wait for the task to complete
            self.reactor.advance(TaskScheduler.SCHEDULE_INTERVAL.as_secs())

        # Both rooms should have been attempted
        self.assertEqual(call_count, 2)

        # The task should complete even with errors
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        # Task should be complete (not failed)
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETE]
        self.assertEqual(len(completed_tasks), 1)

    def test_admin_update_preserves_authenticated_entity(self) -> None:
        """Test that admin updates preserve the authenticated entity in the task."""
        # Create an admin user
        admin_user_id = self.register_user("admin", "adminpass", admin=True)
        admin_user = UserID.from_string(admin_user_id)

        # Admin sets the displayname for another user
        admin_requester = synapse.types.create_requester(
            admin_user,
            authenticated_entity=admin_user_id,
        )

        self.get_success(
            self.handler.set_displayname(
                self.user,
                admin_requester,
                "Admin Set Name",
                by_admin=True,
            )
        )

        # Check the task was scheduled with the admin's authenticated_entity
        tasks = self.get_success(
            self.task_scheduler.get_tasks(
                actions=[UPDATE_JOIN_STATES_ACTION_NAME],
                resource_id=self.user_id,
            )
        )
        self.assertEqual(len(tasks), 1)
        # The task should use the target user's authenticated_entity (since by_admin=True recreates requester)
        self.assertEqual(tasks[0].params.get("requester_authenticated_entity"), admin_user_id)
