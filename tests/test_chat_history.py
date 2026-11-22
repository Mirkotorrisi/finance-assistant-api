"""Chat history: sessions and messages per workspace and user."""

import pytest
from app import app
from fastapi.testclient import TestClient

from src.services.chat_history_service import derive_title

BLUEPRINT = {"name": "Io", "categories": [{"key": "spesa", "label": "Spesa"}]}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def project(client, user="u1"):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}, headers={"X-User-Id": user}).json()
    return {"X-Workspace-Id": str(ws["id"]), "X-User-Id": user}


def say(client, headers, sid, role, content, **extra):
    res = client.post(f"/api/chat-sessions/{sid}/messages", json={"role": role, "content": content, **extra}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_title_is_the_first_words_of_the_first_message():
    assert derive_title("  Quanto ho   speso a marzo? ") == "Quanto ho speso a marzo?"
    long = "Vorrei capire quanto ho speso in totale per la spesa alimentare negli ultimi tre mesi, per favore"
    title = derive_title(long)
    assert title.endswith("…") and len(title) <= 62 and not title.endswith(" …")
    assert title.startswith("Vorrei capire quanto ho speso")


def test_first_message_creates_the_session_and_the_list_is_most_recent_first(client):
    h = project(client)
    first = say(client, h, "s-1", "user", "Quanto ho speso a marzo?", backend="claude")
    assert first["session"]["title"] == "Quanto ho speso a marzo?"
    assert first["session"]["message_count"] == 1 and first["session"]["backend"] == "claude"
    say(client, h, "s-1", "assistant", "320 € in totale.", components=[{"type": "SpendingChart", "order": 0}], tools=["spending_report"])
    say(client, h, "s-2", "user", "Ciao")

    sessions = client.get("/api/chat-sessions", headers=h).json()
    assert [s["id"] for s in sessions] == ["s-2", "s-1"]
    assert sessions[1]["message_count"] == 2

    full = client.get("/api/chat-sessions/s-1", headers=h).json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
    assert full["messages"][1]["components"] == [{"type": "SpendingChart", "order": 0}]
    assert full["messages"][1]["tools"] == ["spending_report"]


def test_an_assistant_error_is_kept_with_the_turn(client):
    h = project(client)
    say(client, h, "s-1", "user", "Ciao")
    say(client, h, "s-1", "assistant", "", error="The agent did not answer within 180s.")
    full = client.get("/api/chat-sessions/s-1", headers=h).json()
    assert full["messages"][1]["error"].startswith("The agent did not answer")


def test_sessions_are_personal_and_scoped_to_the_workspace(client):
    mine = project(client, "u1")
    say(client, mine, "s-1", "user", "Segreto")

    # another user in another project sees nothing and cannot read or hijack the id
    other = project(client, "u2")
    assert client.get("/api/chat-sessions", headers=other).json() == []
    assert client.get("/api/chat-sessions/s-1", headers=other).status_code == 404
    res = client.post("/api/chat-sessions/s-1/messages", json={"role": "user", "content": "x"}, headers=other)
    assert res.status_code in (403, 404)

    # the same user in another of their projects does not see it either
    second = project(client, "u1")
    assert client.get("/api/chat-sessions", headers=second).json() == []

    # and an anonymous caller in the first project (if it were open) is not the owner
    assert client.get("/api/chat-sessions/s-1", headers={"X-Workspace-Id": mine["X-Workspace-Id"]}).status_code in (403, 404)


def test_rename_delete_and_clear(client):
    h = project(client)
    say(client, h, "s-1", "user", "Uno")
    say(client, h, "s-2", "user", "Due")
    renamed = client.patch("/api/chat-sessions/s-1", json={"title": "  Spese di marzo  "}, headers=h)
    assert renamed.status_code == 200 and renamed.json()["title"] == "Spese di marzo"
    assert client.patch("/api/chat-sessions/s-1", json={"title": "   "}, headers=h).status_code == 422

    assert client.delete("/api/chat-sessions/s-1", headers=h).status_code == 200
    assert client.get("/api/chat-sessions/s-1", headers=h).status_code == 404
    assert client.delete("/api/chat-sessions/s-1", headers=h).status_code == 404
    assert [s["id"] for s in client.get("/api/chat-sessions", headers=h).json()] == ["s-2"]

    assert client.delete("/api/chat-sessions", headers=h).json() == {"deleted": 1}
    assert client.get("/api/chat-sessions", headers=h).json() == []


def test_search_matches_title_and_message_text(client):
    h = project(client)
    say(client, h, "s-1", "user", "Quanto ho speso in ristoranti?")
    say(client, h, "s-1", "assistant", "Circa 210 euro da Pizzeria Da Mario.")
    say(client, h, "s-2", "user", "Crea un conto risparmi")
    assert [s["id"] for s in client.get("/api/chat-sessions", params={"search": "mario"}, headers=h).json()] == ["s-1"]
    assert [s["id"] for s in client.get("/api/chat-sessions", params={"search": "RISPARMI"}, headers=h).json()] == ["s-2"]
    assert client.get("/api/chat-sessions", params={"search": "zzz"}, headers=h).json() == []


def test_transcript_is_the_latest_messages_within_a_budget(client):
    h = project(client)
    for i in range(6):
        say(client, h, "s-1", "user", f"domanda {i}")
        say(client, h, "s-1", "assistant", f"risposta {i}")
    t = client.get("/api/chat-sessions/s-1/transcript", params={"max_messages": 4}, headers=h).json()["messages"]
    assert t == [
        {"role": "user", "content": "domanda 4"},
        {"role": "assistant", "content": "risposta 4"},
        {"role": "user", "content": "domanda 5"},
        {"role": "assistant", "content": "risposta 5"},
    ]
    small = client.get("/api/chat-sessions/s-1/transcript", params={"max_chars": 200}, headers=h).json()["messages"]
    assert small and small[-1] == {"role": "assistant", "content": "risposta 5"}
    assert sum(len(m["content"]) for m in small) <= 200
    # unknown session or another user's: empty, never an error
    assert client.get("/api/chat-sessions/nope/transcript", headers=h).json() == {"messages": []}
    other = project(client, "u2")
    assert client.get("/api/chat-sessions/s-1/transcript", headers=other).json() == {"messages": []}


def test_bad_ids_and_roles_are_refused(client):
    h = project(client)
    assert client.post("/api/chat-sessions/a%2Fb/messages", json={"role": "user", "content": "x"}, headers=h).status_code in (404, 422)
    assert client.post("/api/chat-sessions/s-1/messages", json={"role": "system", "content": "x"}, headers=h).status_code == 422
