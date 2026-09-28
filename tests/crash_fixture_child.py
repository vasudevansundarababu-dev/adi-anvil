"""Test-only child: abruptly terminates itself at a selected deterministic fixture graph step."""

import os
import signal
import sys

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row

from anvil import worker
from anvil.config import setting
from anvil.db import one, transaction
from anvil.evaluation import GRAPH_VERSION

project, job_id, crash_stage = sys.argv[1:]
assert crash_stage in ("validate_authorization", "invoke_fixture_capture_output")
with transaction(project, worker=True) as c:
    job = one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (job_id,))
    episode = worker.guard(c, job)
    assert episode["graph_version"] == GRAPH_VERSION and episode["invocation_count"] == 0
with psycopg.connect(
    setting("WORKER_DATABASE_URL"),
    autocommit=True,
    row_factory=dict_row,
    options="-c search_path=anvil_checkpoints",
) as connection:
    saver = PostgresSaver(connection, serde=JsonPlusSerializer(pickle_fallback=False))
    graph = worker.graph_for(job, saver)
    state = {
        "episode_id": str(episode["id"]),
        "project_id": project,
        "graph_version": GRAPH_VERSION,
        "output_artifact_id": None,
    }
    config = {"configurable": {"thread_id": str(episode["thread_id"])}, "recursion_limit": 20}
    for event in graph.stream(state, config, stream_mode="updates"):
        if crash_stage in event:
            os.kill(os.getpid(), signal.SIGKILL)
raise RuntimeError("Expected crash point was not reached")
