"""Outils partagés par les tests : base de test et faux serveur de flux."""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from gazette.db import connexion

DSN = os.environ.get("GAZETTE_TEST_DSN")
FIXTURE = Path(__file__).parent / "fixtures" / "lemonde_une.xml"


@pytest.fixture
def conn():
    """Une connexion dans un schéma `test` vidé : les tests ne touchent jamais aux vraies tables."""
    if not DSN:
        pytest.skip("GAZETTE_TEST_DSN non défini : pas de base de test")
    with connexion(DSN) as c:
        c.execute("DROP SCHEMA IF EXISTS test CASCADE")
        c.execute("CREATE SCHEMA test")
        c.execute("SET search_path TO test")
        c.commit()
        yield c


class FauxEditeur(BaseHTTPRequestHandler):
    """Sert /flux.xml avec un ETag (et 304 si inchangé), /absent en 404, /panne en 503."""

    ETAG = '"v1"'
    appels: ClassVar[list[str]] = []

    def do_GET(self):  # nom imposé par http.server
        FauxEditeur.appels.append(self.path)
        if self.path == "/flux.xml":
            if self.headers.get("If-None-Match") == self.ETAG:
                self.send_response(304)
                self.end_headers()
                return
            corps = FIXTURE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.send_header("ETag", self.ETAG)
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
        elif self.path == "/panne":
            self.send_response(503)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # pas de bruit dans la sortie des tests
        pass


@pytest.fixture
def editeur():
    """Un faux serveur HTTP local ; renvoie son adresse de base, ex. http://127.0.0.1:41234."""
    FauxEditeur.appels = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), FauxEditeur)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_port}"
    serveur.shutdown()
