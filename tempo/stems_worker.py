"""Separate a song into instruments with Demucs, in its own process so the window stays responsive.

    Tempo --stems-worker <song file> <output folder> <model> <progress file>
    python run_tempo.py --stems-worker ...            (Python version)

Writes lines "PROGRESS <0-100>", "STATUS <text>", and finally "DONE <json list>" or
"ERROR <text>" to the progress file (and to stdout when there is one).
"""
import json
import os
import sys


def run(argv):
    src, outdir, model_name = argv[0], argv[1], argv[2]
    prog_path = argv[3] if len(argv) > 3 else None
    prog = open(prog_path, 'a', encoding='utf-8') if prog_path else None

    def emit(line):
        if prog:
            prog.write(line + '\n')
            prog.flush()
        if sys.stdout is not None:
            try:
                print(line, flush=True)
            except Exception:
                pass

    if prog and os.environ.get('TEMPO_DEBUG'):
        import faulthandler
        faulthandler.dump_traceback_later(120, repeat=True, file=prog)
    try:
        _separate(src, outdir, model_name, emit)
        return 0
    except Exception as e:
        emit('ERROR %s: %s' % (type(e).__name__, e))
        return 1
    finally:
        if prog:
            prog.close()


def _separate(src, outdir, model_name, emit):
    emit('PROGRESS 1')
    try:  # python.org builds on Mac ship without root certificates; needed for the model download
        import certifi
        os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    except ImportError:
        pass
    emit('STATUS Starting the separation engine')
    import numpy as np
    import torch
    import tqdm as _tqdm
    import demucs.apply as dapply
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    from tempo.audio import decode, write_wav

    emit('STATUS Loading the separation model (downloads once, about 80-160 MB)')
    model = get_model(model_name)
    model.eval()
    sr = int(model.samplerate)
    emit('STATUS Reading the song')
    audio = decode(src, sr)
    wav = torch.from_numpy(np.ascontiguousarray(audio.T, dtype=np.float32))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    emit('STATUS Separating instruments on the %s (a few minutes)' % ('graphics card' if device == 'cuda' else 'processor'))

    class Progress(_tqdm.tqdm):
        def __init__(self, *a, **k):
            k['file'] = open(os.devnull, 'w')
            super().__init__(*a, **k)

        def __iter__(self):
            total = self.total or 0
            for i, x in enumerate(super().__iter__()):
                yield x
                if total:
                    emit('PROGRESS %d' % (5 + 90 * (i + 1) / total))

    if hasattr(dapply, 'tqdm'):
        dapply.tqdm.tqdm = Progress
    with torch.no_grad():
        out = apply_model(model, wav[None], device=device, shifts=1, split=True, overlap=0.25, progress=True)[0]
    out = out * std + mean
    os.makedirs(outdir, exist_ok=True)
    names = []
    for name, s in zip(model.sources, out):
        write_wav(os.path.join(outdir, name + '.wav'), s.cpu().numpy().T, sr)
        names.append(name)
    emit('PROGRESS 100')
    emit('DONE ' + json.dumps(names))


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(run(sys.argv[1:]))
