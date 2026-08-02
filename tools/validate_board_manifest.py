#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "protobuf>=6.31.1",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly after `make`:
#      uv run tools/validate_board_manifest.py
# 3. Or run with the repository Python environment:
#      python3 tools/validate_board_manifest.py
# ──────────────────

from __future__ import annotations

import importlib
import json
import os
import re
import sys
import types
from pathlib import Path

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message as ProtoMessage


ROOT = Path(__file__).resolve().parents[1]
BOARD_DIR = ROOT / "whad" / "protocol" / "board"
PROTO_PATH = BOARD_DIR / "board.proto"
OPTIONS_PATH = BOARD_DIR / "board.options"
MANIFEST_PATH = BOARD_DIR / "board_manifest.json"
PYTHON_DIST = ROOT / "dist" / "python"
sys.dont_write_bytecode = True

EXPECTED_COMMANDS = [
    "GetBoardInfo",
    "ListSensors",
    "ReadSensor",
    "ConfigureStream",
    "StopStream",
    "Calibrate",
    "GetCalibration",
    "SetOutput",
    "GetInputState",
    "ConfigureInput",
    "I2cTransfer",
    "GpioConfigure",
    "GpioRead",
    "GpioWrite",
    "AdcRead",
    "SpiTransfer",
    "StorageInfo",
    "StorageAdopt",
    "StorageReadLog",
    "StorageEraseLog",
    "GetRuntimeConfig",
    "SetRuntimeConfig",
    "SetRuntimeMode",
    "RemoteProfileGet",
    "RemoteProfileSet",
    "AudioConfigure",
    "ReleasePin",
    "RawPcmDiagnostics",
]


def fail(message: str) -> None:
    print(f"board manifest validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest():
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_board_commands(proto_text: str) -> dict[str, int]:
    enum_match = re.search(r"enum\s+BoardCommand\s*\{(?P<body>.*?)\n\}", proto_text, re.S)
    if enum_match is None:
        fail("BoardCommand enum is missing")
    commands: dict[str, int] = {}
    for name, value in re.findall(r"^\s*(\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*;", enum_match.group("body"), re.M):
        commands[name] = int(value, 0)
    return commands


def parse_oneof_tags(proto_text: str) -> dict[str, int]:
    message_match = re.search(r"message\s+Message\s*\{(?P<body>.*?)\n\}", proto_text, re.S)
    if message_match is None:
        fail("board.Message is missing")
    oneof_match = re.search(r"oneof\s+msg\s*\{(?P<body>.*?)\n\s*\}", message_match.group("body"), re.S)
    if oneof_match is None:
        fail("board.Message oneof msg is missing")
    tags: dict[str, int] = {}
    for _, field_name, tag in re.findall(r"^\s*(\w+)\s+(\w+)\s*=\s*(\d+)\s*;", oneof_match.group("body"), re.M):
        tags[field_name] = int(tag)
    return tags


def parse_variable_fields(proto_text: str) -> set[str]:
    fields: set[str] = set()
    for message_name, body in re.findall(r"message\s+(\w+)\s*\{(.*?)\n\}", proto_text, re.S):
        if message_name == "Message":
            continue
        for repeated, field_type, field_name in re.findall(
            r"^\s*(repeated\s+)?(?:optional\s+)?(\w+)\s+(\w+)\s*=\s*\d+",
            body,
            re.M,
        ):
            if repeated or field_type in {"bytes", "string"}:
                fields.add(f"board.{message_name}.{field_name}")
    return fields


def parse_options() -> set[str]:
    constrained: set[str] = set()
    for line in OPTIONS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, tail = stripped.partition(" ")
        if "max_size" in tail or "max_count" in tail:
            constrained.add(key)
    return constrained


def validate_manifest(proto_text: str) -> None:
    manifest = load_manifest()
    proto_commands = parse_board_commands(proto_text)
    if [name for name, _ in sorted(proto_commands.items(), key=lambda item: item[1])] != EXPECTED_COMMANDS:
        fail("BoardCommand enum does not match the canonical 28-command order")

    manifest_commands = manifest.get("commands", [])
    if len(manifest_commands) != len(EXPECTED_COMMANDS):
        fail("manifest does not list exactly 28 commands")

    command_ids = [command.get("id") for command in manifest_commands]
    command_names = [command.get("name") for command in manifest_commands]
    if command_ids != list(range(len(EXPECTED_COMMANDS))):
        fail("manifest command IDs are not exactly 0..27")
    if command_names != EXPECTED_COMMANDS:
        fail("manifest command names do not match BoardCommand order")
    if len(set(command_names)) != len(command_names):
        fail("manifest contains duplicate command names")

    proto_oneof_tags = parse_oneof_tags(proto_text)
    manifest_oneof_tags = manifest.get("oneof_tags", {})
    if proto_oneof_tags != manifest_oneof_tags:
        fail("manifest oneof tags do not match board.Message")
    if min(proto_oneof_tags.values()) != 2:
        fail("board.Message oneof tags must start at 2 because request_id owns tag 1")
    if len(set(proto_oneof_tags.values())) != len(proto_oneof_tags):
        fail("board.Message contains duplicate oneof tags")

    for command in manifest_commands:
        request = command.get("request")
        terminal = command.get("terminal", [])
        if request not in manifest_oneof_tags:
            fail(f"{command.get('name')} request {request!r} is not a board.Message field")
        if len(terminal) != 1:
            fail(f"{command.get('name')} must declare exactly one terminal path")
        if terminal[0] not in manifest_oneof_tags:
            fail(f"{command.get('name')} terminal {terminal[0]!r} is not a board.Message field")
        start = command.get("start")
        if start is not None and start not in manifest_oneof_tags:
            fail(f"{command.get('name')} start {start!r} is not a board.Message field")

    sensor_ids = [sensor.get("id") for sensor in manifest.get("sensors", [])]
    if sensor_ids != list(range(1, 15)):
        fail("sensor descriptor manifest IDs are not exactly 1..14")


def validate_options(proto_text: str) -> None:
    variable_fields = parse_variable_fields(proto_text)
    constrained_fields = parse_options()
    missing = sorted(variable_fields - constrained_fields)
    if missing:
        fail("unbounded board fields: " + ", ".join(missing))


def option_value(options: set[str], key: str, option_name: str, default: int) -> int:
    prefix = f"{key} "
    for line in OPTIONS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            match = re.search(rf"{option_name}\s*:\s*(\d+)", stripped)
            if match is not None:
                return int(match.group(1))
    if key in options:
        return default
    return default


def fill_message(message: ProtoMessage, options: set[str]) -> None:
    for field in message.DESCRIPTOR.fields:
        field_key = f"board.{message.DESCRIPTOR.name}.{field.name}"
        count = option_value(options, field_key, "max_count", 1)
        size = option_value(options, field_key, "max_size", 8)
        if field.is_repeated:
            repeated_values = getattr(message, field.name)
            for _ in range(count):
                if field.message_type is not None:
                    child = repeated_values.add()
                    fill_message(child, options)
                elif field.type == FieldDescriptor.TYPE_STRING:
                    repeated_values.append("x" * size)
                elif field.type == FieldDescriptor.TYPE_BYTES:
                    repeated_values.append(b"x" * size)
                else:
                    repeated_values.append(1)
            continue
        if field.message_type is not None:
            fill_message(getattr(message, field.name), options)
        elif field.type == FieldDescriptor.TYPE_STRING:
            setattr(message, field.name, "x" * size)
        elif field.type == FieldDescriptor.TYPE_BYTES:
            setattr(message, field.name, b"x" * size)
        elif field.type == FieldDescriptor.TYPE_BOOL:
            setattr(message, field.name, True)
        elif field.type == FieldDescriptor.TYPE_ENUM:
            setattr(message, field.name, 1)
        else:
            setattr(message, field.name, 1)


def validate_encoded_sizes() -> None:
    if not PYTHON_DIST.exists():
        fail("dist/python is missing; run make before validation")
    sys.path.insert(0, str(PYTHON_DIST))
    os.environ["TEMPORARILY_DISABLE_PROTOBUF_VERSION_CHECK"] = "true"
    install_generated_namespace()
    whad_pb2 = importlib.import_module("whad.protocol.whad_pb2")
    board_pb2 = importlib.import_module("whad.protocol.board.board_pb2")
    manifest = load_manifest()
    limit = manifest["encoded_message_limit"]
    options = parse_options()
    oversize: list[str] = []

    for field in board_pb2.Message.DESCRIPTOR.oneofs_by_name["msg"].fields:
        root_message = whad_pb2.Message()
        root_message.board.request_id = 1
        payload = getattr(root_message.board, field.name)
        fill_message(payload, options)
        encoded_size = len(root_message.SerializeToString())
        if encoded_size > limit:
            oversize.append(f"{field.name}={encoded_size}")
    if oversize:
        fail("encoded root messages exceed limit: " + ", ".join(oversize))


def package_module(name: str, path: Path) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    return module


def install_generated_namespace() -> None:
    sys.modules["whad"] = package_module("whad", PYTHON_DIST / "whad")
    sys.modules["whad.protocol"] = package_module("whad.protocol", PYTHON_DIST / "whad" / "protocol")
    for package_name in ("ble", "board", "dot15d4", "esb", "phy", "unifying"):
        full_name = f"whad.protocol.{package_name}"
        package_path = PYTHON_DIST / "whad" / "protocol" / package_name
        sys.modules[full_name] = package_module(full_name, package_path)


def main() -> None:
    proto_text = PROTO_PATH.read_text(encoding="utf-8")
    validate_manifest(proto_text)
    validate_options(proto_text)
    validate_encoded_sizes()
    print("board manifest validation passed")


if __name__ == "__main__":
    main()
