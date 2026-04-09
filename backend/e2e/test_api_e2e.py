"""
End-to-end API tests: real FastAPI app + temp SQLite + HTTP (TestClient).

Main user journeys (OpenAI-backed routes use unittest.mock — no API key required).

Run from the `backend` directory (see RUN_E2E.txt).

Must set STUDY_ASSISTANT_DATA_DIR before `main` / `config` load.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

_TMP_DATA = tempfile.mkdtemp()
os.environ["STUDY_ASSISTANT_DATA_DIR"] = _TMP_DATA

from fastapi.testclient import TestClient

from main import app


def _study_txt() -> tuple[str, bytes, str]:
    return ("notes.txt", b"Study material for quiz, chat, and flashcard generation.", "text/plain")


class _E2EBase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(_TMP_DATA, ignore_errors=True)


class TestJourneyHealthDeckDocument(_E2EBase):
    """Deck + document: health, create, upload, get, list, rename, remove doc, delete deck."""

    def test_flow(self) -> None:
        with TestClient(app) as client:
            h = client.get("/api/health")
            self.assertEqual(h.status_code, 200)
            self.assertTrue(h.json().get("ok"))

            c = client.post("/api/decks", json={"name": "Journey Deck"})
            self.assertEqual(c.status_code, 200, c.text)
            deck_id = c.json()["id"]

            name, data, mime = _study_txt()
            up = client.post(
                f"/api/decks/{deck_id}/document",
                files={"file": (name, data, mime)},
            )
            self.assertEqual(up.status_code, 200, up.text)
            self.assertTrue(up.json().get("has_study_material"))

            rn = client.put(f"/api/decks/{deck_id}", json={"name": "Renamed Deck"})
            self.assertEqual(rn.status_code, 200, rn.text)
            self.assertEqual(rn.json()["name"], "Renamed Deck")

            rm = client.delete(f"/api/decks/{deck_id}/document")
            self.assertEqual(rm.status_code, 200, rm.text)
            self.assertFalse(rm.json().get("has_study_material"))

            client.post(
                f"/api/decks/{deck_id}/document",
                files={"file": (_study_txt()[0], _study_txt()[1], _study_txt()[2])},
            )

            d = client.delete(f"/api/decks/{deck_id}")
            self.assertEqual(d.status_code, 200, d.text)
            self.assertTrue(d.json().get("deleted"))


class TestJourneyFlashcardsManual(_E2EBase):
    """Create deck → add flashcard → list → review → update → delete."""

    def test_flow(self) -> None:
        with TestClient(app) as client:
            deck_id = client.post("/api/decks", json={"name": "FC Deck"}).json()["id"]

            fc = client.post(
                f"/api/decks/{deck_id}/flashcards",
                json={"front": "Question?", "back": "Answer."},
            )
            self.assertEqual(fc.status_code, 200, fc.text)
            fc_id = fc.json()["id"]

            lst = client.get(f"/api/decks/{deck_id}/flashcards")
            self.assertEqual(lst.status_code, 200)
            self.assertEqual(len(lst.json()), 1)

            rv = client.post(
                f"/api/decks/{deck_id}/flashcards/{fc_id}/review",
                json={"rating": "good"},
            )
            self.assertEqual(rv.status_code, 200, rv.text)
            self.assertIsNotNone(rv.json().get("sm2_next_review_at"))

            ed = client.put(
                f"/api/decks/{deck_id}/flashcards/{fc_id}",
                json={"front": "Q2", "back": "A2"},
            )
            self.assertEqual(ed.status_code, 200, ed.text)
            self.assertEqual(ed.json()["front"], "Q2")

            dl = client.delete(f"/api/decks/{deck_id}/flashcards/{fc_id}")
            self.assertEqual(dl.status_code, 200)
            self.assertTrue(dl.json().get("deleted"))


class TestJourneyFlashcardGenerateMocked(_E2EBase):
    """Deck + study text → AI flashcard generate (mocked) → cards exist."""

    def test_flow(self) -> None:
        with TestClient(app) as client:
            deck_id = client.post("/api/decks", json={"name": "Gen Deck"}).json()["id"]
            n, d, m = _study_txt()
            client.post(f"/api/decks/{deck_id}/document", files={"file": (n, d, m)})

            with patch("main.generate_flashcards", new_callable=AsyncMock) as gen:
                gen.return_value = [{"front": "F1", "back": "B1"}, {"front": "F2", "back": "B2"}]
                r = client.post(f"/api/decks/{deck_id}/flashcards/generate")

            self.assertEqual(r.status_code, 200, r.text)
            gen.assert_awaited_once()
            cards = r.json()
            self.assertGreaterEqual(len(cards), 2)
            fronts = {c["front"] for c in cards}
            self.assertIn("F1", fronts)
            self.assertIn("F2", fronts)


class TestJourneyQuizMocked(_E2EBase):
    """Deck + material → quiz generate (mocked) → quiz grade (MC only, no LLM)."""

    def test_flow(self) -> None:
        with TestClient(app) as client:
            deck_id = client.post("/api/decks", json={"name": "Quiz Deck"}).json()["id"]
            n, d, m = _study_txt()
            client.post(f"/api/decks/{deck_id}/document", files={"file": (n, d, m)})

            fake_mc = [
                {
                    "id": "mc1",
                    "type": "multiple_choice",
                    "question": "Pick B",
                    "options": ["wrong", "right"],
                    "correct_index": 1,
                }
            ]

            with patch("main.generate_quiz", new_callable=AsyncMock) as gq:
                gq.return_value = (fake_mc, [])
                qg = client.post(
                    f"/api/decks/{deck_id}/quiz/generate",
                    json={"num_multiple_choice": 1, "num_short_answer": 0},
                )

            self.assertEqual(qg.status_code, 200, qg.text)
            gq.assert_awaited_once()
            questions = qg.json().get("questions") or []
            self.assertTrue(questions)

            gr = client.post(
                f"/api/decks/{deck_id}/quiz/grade",
                json={
                    "questions": questions,
                    "answers": [
                        {
                            "question_id": "mc1",
                            "question_type": "multiple_choice",
                            "user_answer": 1,
                        }
                    ],
                },
            )
            self.assertEqual(gr.status_code, 200, gr.text)
            res = gr.json()
            self.assertEqual(res.get("correct_count"), 1)
            self.assertEqual(res.get("total_count"), 1)


class TestJourneyChatMocked(_E2EBase):
    """Chat session → send message (assistant reply mocked) → list messages & sessions."""

    def test_flow(self) -> None:
        with TestClient(app) as client:
            deck_id = client.post("/api/decks", json={"name": "Chat Deck"}).json()["id"]

            cs = client.post(f"/api/decks/{deck_id}/chat/sessions")
            self.assertEqual(cs.status_code, 200, cs.text)
            sid = cs.json()["id"]

            with patch("main.learning_chat", new_callable=AsyncMock) as lc:
                lc.return_value = "Here is a helpful reply."
                with patch("main.suggest_chat_session_title", new_callable=AsyncMock) as st:
                    st.return_value = "Test topic"
                    msg = client.post(
                        f"/api/decks/{deck_id}/chat/sessions/{sid}/messages",
                        json={"message": "What is this deck about?"},
                    )

            self.assertEqual(msg.status_code, 200, msg.text)
            lc.assert_awaited()
            self.assertIn("helpful reply", msg.json().get("content", ""))

            msgs = client.get(f"/api/decks/{deck_id}/chat/sessions/{sid}/messages")
            self.assertEqual(msgs.status_code, 200)
            rows = msgs.json()
            self.assertGreaterEqual(len(rows), 2)

            sl = client.get(f"/api/decks/{deck_id}/chat/sessions")
            self.assertEqual(sl.status_code, 200)
            self.assertTrue(any(s["id"] == sid for s in sl.json()))

            dl = client.delete(f"/api/decks/{deck_id}/chat/sessions/{sid}")
            self.assertEqual(dl.status_code, 200)
            self.assertTrue(dl.json().get("deleted"))


if __name__ == "__main__":
    unittest.main()
