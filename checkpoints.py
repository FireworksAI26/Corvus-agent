"""Checkpoints: snapshot the agent's learned state by name.

Corvus's self-improvement lives in the .memory directory (lessons, episodes,
notes, skills) - not in model weights. A checkpoint is a full copy of that
folder, so you can save an agent you like and start new conversations from
that exact state anytime.
"""
import json
import os
import shutil
import time

CHECKPOINT_DIR = ".checkpoints"


def save(name: str, memory_path: str = ".memory") -> str:
    if not os.path.isdir(memory_path):
        raise ValueError("No memory to checkpoint yet - run some tasks first")
    dest = os.path.join(CHECKPOINT_DIR, name)
    if os.path.exists(dest):
        raise ValueError(f"Checkpoint '{name}' already exists")
    shutil.copytree(memory_path, dest)
    with open(os.path.join(dest, "checkpoint.json"), "w") as f:
        json.dump({"name": name, "created": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    return dest


def list_checkpoints() -> list[str]:
    if not os.path.isdir(CHECKPOINT_DIR):
        return []
    out = []
    for name in sorted(os.listdir(CHECKPOINT_DIR)):
        meta_path = os.path.join(CHECKPOINT_DIR, name, "checkpoint.json")
        created = ""
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                created = json.load(f).get("created", "")
        out.append(f"{name}  (saved {created})")
    return out


def load(name: str, memory_path: str = ".memory") -> str:
    """Restore a checkpoint. Current memory is kept at <memory_path>.backup."""
    src = os.path.join(CHECKPOINT_DIR, name)
    if not os.path.isdir(src):
        raise ValueError(f"No checkpoint named '{name}'")
    if os.path.isdir(memory_path):
        backup = f"{memory_path}.backup"
        shutil.rmtree(backup, ignore_errors=True)
        shutil.move(memory_path, backup)
    shutil.copytree(src, memory_path)
    meta = os.path.join(memory_path, "checkpoint.json")
    if os.path.exists(meta):
        os.remove(meta)
    return memory_path
