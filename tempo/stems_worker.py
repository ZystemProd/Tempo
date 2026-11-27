"""Separate a song into instruments with Demucs. Runs as its own process:

    python -m tempo.stems_worker <song file> <output folder> <model>

Prints progress lines "PROGRESS <0-100>" and finally "DONE <json list of stem names>".
"""
import json
import os
import sys


def main():
    src, outdir, model_name = sys.argv[1], sys.argv[2], sys.argv[3]
    print('PROGRESS 1', flush=True)
    try:  # python.org builds on Mac ship without root certificates; needed for the model download
        import certifi
        os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    except ImportError:
        pass
    import numpy as np
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tempo.audio import decode, write_wav

    print('STATUS Loading the separation model (downloads once, about 80-160 MB)', flush=True)
    model = get_model(model_name)
    model.eval()
    sr = int(model.samplerate)
    print('STATUS Reading the song', flush=True)
    audio = decode(src, sr)
    wav = torch.from_numpy(np.ascontiguousarray(audio.T, dtype=np.float32))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print('STATUS Separating instruments on %s (this takes a few minutes)' % ('graphics card' if device == 'cuda' else 'processor'), flush=True)

    # Report progress by wrapping tqdm, which Demucs uses internally.
    import tqdm as _tqdm

    class Progress(_tqdm.tqdm):
        def __iter__(self):
            total = self.total or 0
            for i, x in enumerate(super().__iter__()):
                yield x
                if total:
                    print('PROGRESS %d' % (5 + 90 * (i + 1) / total), flush=True)

    import demucs.apply as dapply
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
    print('PROGRESS 100', flush=True)
    print('DONE ' + json.dumps(names), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR %s: %s' % (type(e).__name__, e), flush=True)
        sys.exit(1)
