"""Seeded, independent random streams and a stable hash helper.

Why not Python's hash()?  For strings, hash() changes in every new Python
process, so a seed built from it would give different data on each run.
SHA-256 always gives the same answer.
"""
import hashlib
import random

from app.config import settings


def derive_seed(stream: str, seed: int | None = None) -> int:
    """Turn (master seed, stream name) into a stable 64-bit integer seed."""
    master = settings.seed if seed is None else seed
    digest = hashlib.sha256(f"{master}:{stream}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def make_rng(stream: str, seed: int | None = None) -> random.Random:
    """Return a private random generator for one named part of the generator.

    Same (seed, stream) -> same sequence, in any process, on any run.
    Different stream names give independent sequences.
    """
    return random.Random(derive_seed(stream, seed))


def make_faker(stream: str, seed: int | None = None, locale: str = "en_IN"):
    """Return a Faker instance seeded for one named stream.

    seed_instance() seeds only this object, not Faker's shared global state.
    """
    from faker import Faker  # imported here so importing this module stays fast

    fake = Faker(locale)
    fake.seed_instance(derive_seed(f"faker:{stream}", seed))
    return fake


def sha256_hex(text: str) -> str:
    """64-character SHA-256 digest of text; used for document file hashes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
