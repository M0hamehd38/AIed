"""Client for the speech-to-text service (stt/). Audio stays in memory: it is sent and then dropped."""
import json
import urllib.error
import urllib.request

from django.conf import settings


class STTUnavailable(Exception):
    pass


# the service is on the internal network: never route it through an HTTP proxy from the environment
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def configured():
    return bool(settings.STT_URL and settings.STT_TOKEN)


def transcribe(audio: bytes, content_type: str) -> str:
    if not configured():
        raise STTUnavailable('not configured')
    req = urllib.request.Request(settings.STT_URL.rstrip('/') + '/transcribe', data=audio, method='POST',
                                 headers={'Content-Type': content_type or 'application/octet-stream',
                                          'X-STT-Token': settings.STT_TOKEN})
    try:
        with _direct.open(req, timeout=settings.STT_TIMEOUT) as r:
            return json.loads(r.read().decode('utf-8')).get('text', '').strip()
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise STTUnavailable(str(e)) from e
