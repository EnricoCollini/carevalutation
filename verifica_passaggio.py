from pathlib import Path
import av
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

_open = av.open
def compatible_open(*a, **kw):
    kw.pop('metadata_errors', None)
    return _open(*a, **kw)
av.open = compatible_open
root = Path(__file__).resolve().parent
p = next(Path(r'C:\Users\io\Downloads').glob('Quanto devi GUADAGNARE*.mp3'))
audio = decode_audio(str(p))
model = WhisperModel(str(root / '.audio-models' / 'small'), device='cpu', compute_type='int8', cpu_threads=4)
segments, _ = model.transcribe(audio[185*16000:248*16000], language='it', beam_size=1, repetition_penalty=1.1, no_repeat_ngram_size=3)
with (root / 'trascrizioni' / 'verifica_primo_03m05s.txt').open('w', encoding='utf-8') as f:
    for s in segments:
        line = f'[{s.start+185:.1f}] {s.text.strip()}'
        f.write(line+'\n')
        f.flush()
        print(line, flush=True)
