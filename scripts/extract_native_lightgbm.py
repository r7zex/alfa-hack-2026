"""Extract the single known native model using passive pickle opcode inspection.

This never imports or executes any class from the uploaded pickle. Only the exact
user-provided source hash and exact expected native model hash are accepted.
"""
from pathlib import Path
from hashlib import sha256
import argparse
import pickletools
import zlib
from ml.imported_lightgbm import ARTIFACT_SHA256, SOURCE_JOBLIB_SHA256


def extract(source: Path, destination: Path):
    data = source.read_bytes()
    if sha256(data).hexdigest() != SOURCE_JOBLIB_SHA256:
        raise ValueError('Unexpected source SHA256')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(data, 2_000_000)
    if not decoder.eof or decoder.unconsumed_tail or len(raw) >= 2_000_000:
        raise ValueError('Unsupported compressed payload')
    candidates, strings = [], []
    try:
        for op, value, position in pickletools.genops(raw):
            if isinstance(value, str):
                strings.append(value)
                if value.startswith('tree\n'):
                    candidates.append(value.encode('utf-8'))
    except ValueError as exc:
        # joblib appends raw NumPy arrays, which are not pickle opcodes.
        # The known file's model and pipeline steps are before that boundary.
        if '550282' not in str(exc):
            raise ValueError('Unexpected pickle layout') from exc
    if strings[:7] != ['pipeline', 'sklearn.pipeline', 'Pipeline', 'steps', 'model', 'lightgbm.sklearn', 'LGBMClassifier']:
        raise ValueError('Unexpected Pipeline layout; preprocessing not verified')
    if len(candidates) != 1 or sha256(candidates[0]).hexdigest() != ARTIFACT_SHA256:
        raise ValueError('Native model SHA256 mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != candidates[0]:
        raise ValueError('Refusing to replace different weights')
    destination.write_bytes(candidates[0])
    return ARTIFACT_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(extract(args.source, args.destination))

if __name__ == '__main__':
    main()
