"""Keep orchestration imports separate from the normal application environment."""

import json
import os
from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
# Airflow needs a worker name, not DNS, for its in-process offline test runner.
os.environ["AIRFLOW__CORE__HOSTNAME_CALLABLE"] = "socket.gethostname"
sys.path.insert(0, str(ROOT / "dbt"))
sys.path.insert(0, str(ROOT / "orchestration"))


@pytest.fixture
def config():
    return json.loads((ROOT / "orchestration/folkestone-2019.json").read_text())["snapshot"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline orchestration test attempted network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    import google.auth
    monkeypatch.setattr(google.auth, "default", forbidden)


class Blob:
    def __init__(self, store, uri, generation=None):
        self.store, self.uri, self.generation = store, uri, generation

    def reload(self, **kwargs):
        self.generation, payload = self.store.objects[self.uri]
        self.size = len(payload)

    def download_as_bytes(self, **kwargs):
        generation, payload = self.store.objects[self.uri]
        assert self.generation == generation == kwargs["if_generation_match"]
        self.store.downloads.append((self.uri, generation))
        return payload


class Storage:
    def __init__(self, objects):
        self.objects, self.downloads = objects, []

    def bucket(self, name):
        store = self

        class Bucket:
            def blob(self, path, generation=None):
                return Blob(store, f"gs://{name}/{path}", generation)

        return Bucket()
