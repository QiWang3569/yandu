"""Verify local image bytes before model calls; never fetch URLs from cases."""
import hashlib
from pathlib import Path

from backend.app.vision import image_data


def prepare_assets(cases, root):
    root = Path(root).resolve()
    prepared = {}
    for case in cases:
        if case['task'] != 'vision_draft':
            continue
        images = []
        for asset in case['input']['images']:
            path = (root / asset['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f'{case["id"]}: missing image or path outside assets root')
            if path.stat().st_size > 6 * 1024 * 1024:
                raise ValueError(f'{case["id"]}: image exceeds production 6 MiB limit')
            if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
                raise ValueError(f'{case["id"]}: image SHA256 mismatch')
            try:
                images.append(image_data(path))
            except Exception as exc:
                from fastapi import HTTPException
                if isinstance(exc, HTTPException):
                    raise ValueError(f'{case["id"]}: image cannot be decoded under production limits') from None
                raise
        prepared[case['id']] = images
    return prepared
