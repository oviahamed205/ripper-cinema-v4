"""
tests.unit.test_player_ipc
~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for MPV IPC supervisor and resume checkpointing.
"""

from unittest.mock import patch, MagicMock
from ripper.player.ipc import (
    get_default_ipc_path,
    save_resume_checkpoint,
    get_saved_resume_position,
    MpvIpcClient,
    HISTORY_FILE,
)


def test_get_default_ipc_path():
    path = get_default_ipc_path()
    assert isinstance(path, str)
    assert len(path) > 0


def test_resume_checkpoint_save_and_retrieve(tmp_path):
    test_hist_file = tmp_path / "history.json"
    with patch("ripper.player.ipc.HISTORY_FILE", test_hist_file):
        save_resume_checkpoint(
            title="Interstellar",
            stream_url="https://example.com/interstellar.mp4",
            time_pos=1420.5,
            duration=7200.0,
            portal_id="moviebox",
        )

        pos = get_saved_resume_position("https://example.com/interstellar.mp4")
        assert pos == 1420.5

        # Completed (>90%) title should not resume
        save_resume_checkpoint(
            title="Interstellar Completed",
            stream_url="https://example.com/interstellar.mp4",
            time_pos=7100.0,
            duration=7200.0,
            portal_id="moviebox",
        )
        pos_after = get_saved_resume_position("https://example.com/interstellar.mp4")
        assert pos_after is None


def test_mpv_ipc_client_command_serialization():
    client = MpvIpcClient()
    # Mock pipe handle
    client.is_connected = True
    client._sock = MagicMock()

    res = client.send_command(["get_property", "time-pos"])
    assert res == {"status": "sent"}
    assert client._sock.sendall.called

    client.close()
    assert client.is_connected is False
