"""Speech-to-text service for Classyar. Runs on the university's own server, beside the panel.

- Takes one short audio chunk, returns its Persian text. The audio is decoded in memory and never written to disk.
- Only the panel can call it (shared token); it is not meant to be reachable from the internet.
- Configuration: STT_TOKEN (required), WHISPER_MODEL (default "small"), WHISPER_DEVICE ("auto" | "cpu" | "cuda"),
  WHISPER_COMPUTE ("default", or e.g. "int8" on CPU / "float16" on GPU). Models are cached under HF_HOME.
"""
import hmac
import io
import os
import threading

from fastapi import FastAPI, Header, HTTPException, Request

MAX_BYTES = 4 * 1024 * 1024  # a chunk is a few seconds of compressed audio
TOKEN = os.environ.get('STT_TOKEN', '')
app = FastAPI(title='classyar-stt', docs_url=None, redoc_url=None, openapi_url=None)

_model, _lock = None, threading.Lock()


def model():
    """Load the model once, on first use (large models take a while)."""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(os.environ.get('WHISPER_MODEL', 'small'),
                                  device=os.environ.get('WHISPER_DEVICE', 'auto'),
                                  compute_type=os.environ.get('WHISPER_COMPUTE', 'default'))
        return _model


def transcribe_bytes(data: bytes) -> dict:
    segments, info = model().transcribe(io.BytesIO(data), language='fa', vad_filter=True, beam_size=1,
                                        condition_on_previous_text=False)
    text = ' '.join(s.text.strip() for s in segments).strip()
    return {'text': text, 'duration': round(info.duration, 2)}


@app.get('/health')
def health():
    return {'ok': True, 'model_loaded': _model is not None}


@app.post('/transcribe')
async def transcribe(request: Request, x_stt_token: str = Header(default='')):
    if not TOKEN or not hmac.compare_digest(x_stt_token, TOKEN):
        raise HTTPException(status_code=401)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail='empty audio')
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413)
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(transcribe_bytes, data)
