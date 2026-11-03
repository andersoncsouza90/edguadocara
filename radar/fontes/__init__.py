"""Fontes primárias monitoradas pelo radar."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "radar-concursos/0.1 (+https://github.com/andersoncsouza90/edguadocara)"


def http_get(url: str, params: dict | None = None, timeout: int = 30, tentativas: int = 4) -> str:
    """GET com retentativa e backoff exponencial (2s, 4s, 8s...)."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR"})
    erro: Exception | None = None
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            erro = e
        except (urllib.error.URLError, TimeoutError) as e:
            erro = e
        time.sleep(2 ** (i + 1))
    raise RuntimeError(f"Falha ao baixar {url}: {erro}")


def http_json(url: str, params: dict | None = None, **kw) -> dict:
    return json.loads(http_get(url, params, **kw))
