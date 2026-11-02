"""Tests proving the random streams are repeatable, independent and process-stable."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from app.config import settings
from generator.rng import derive_seed, make_faker, make_rng, sha256_hex

BACKEND_DIR = Path(__file__).resolve().parents[1]


def take(rng, n=10):
    return [rng.random() for _ in range(n)]


def test_same_seed_and_stream_gives_same_numbers():
    assert take(make_rng("customers", 123)) == take(make_rng("customers", 123))


def test_different_streams_give_different_numbers():
    assert take(make_rng("customers", 123)) != take(make_rng("documents", 123))


def test_different_seeds_give_different_numbers():
    assert take(make_rng("customers", 1)) != take(make_rng("customers", 2))


def test_streams_are_independent_of_each_other():
    """Using one stream heavily must not change what another stream produces."""
    clean = take(make_rng("documents", 123))

    customers = make_rng("customers", 123)
    take(customers, 5000)  # consume a lot from a different stream
    after_other_use = take(make_rng("documents", 123))

    assert clean == after_other_use


def test_default_seed_comes_from_settings():
    assert settings.seed == 20261022
    assert derive_seed("customers") == derive_seed("customers", 20261022)


def test_numbers_are_identical_across_processes_with_different_hash_seeds():
    """The trap test: Python randomizes hash() per process, ours must not care."""
    code = (
        "from generator.rng import make_rng; "
        "r = make_rng('customers'); "
        "print([r.random() for _ in range(3)])"
    )
    outputs = []
    for hash_seed in ("1", "2", "random"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True,
        )
        outputs.append(result.stdout.strip())
    assert outputs[0] == outputs[1] == outputs[2]
    assert outputs[0]  # not empty


def test_faker_same_stream_gives_same_names():
    first = make_faker("customers", 123)
    second = make_faker("customers", 123)
    assert [first.name() for _ in range(5)] == [second.name() for _ in range(5)]


def test_sha256_hex_matches_known_value():
    # Standard published SHA-256 test vector for the text "abc".
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_hex("abc") == expected
    assert sha256_hex("abc") == hashlib.sha256(b"abc").hexdigest()
    assert len(sha256_hex("anything")) == 64
