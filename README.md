Open protocol for wireless hacking tools
========================================

This project is still a work in progress and could change
at any time.

Objectives
----------

This protocol has the main objective to allow interoperability between hardware RF devices and
wireless (hacking) tools, independantly of the supported technology. Other objectives include
but are not limited to:

* to provide a protocol that can be implemented in various programming languages
* to optimize the size of the exchanged data
* to allow new features/protocols to be easily added (evolutivity)

Design choices
--------------

This protocol relies on Protocol Buffers because it is supported by a lot of programming
languages, provides a way to model messages and optimized serialization/deserialization. 

However, we added an overlay to allow fragmented chunks of data to be sent and received
by devices and host applications.

### Domains

This protocol has been designed to be used with a variety of wireless protocols and therefore
consider each protocol to be a specific *domain* with associated messages. Using separate
*domains* will allow easier integration of new protocols in the future without having to
change the existing messages.

The following domains are currently supported:

* Bluetooth Low Energy
* 802.15.4: used for ZigBee and other derivated protocols such as RF4CE
* Nordic Semiconductor Enhanced ShockBurst: used for ESB and other derivated protocols
* Logitech Unifying
* PHY: support various modulations (*FSK, *PSK, ASK, LoRa)


### Capabilities

Each device that supports this protocol must support a set of generic messages, independently of the supported
wireless protocols. These messages allow:

* to identify the device including its firmware version and its supported communication protocol version
* to query the domains this device supports
* to query its capabilities per supported domain
* to retrieve the list of messages/commands it supports

This discovery step is part of the communication protocol and allows third-party tools to determine if an
hardware device can be used to achieve a specific task, no matter its firmware.

#### Bluetooth Low Energy capabilities

* Low-level capabilities
	* Advertisements sniffing
    * Connection sniffing (capture of connection initiation request)
    * Connection sniffing (passive monitoring)
    * direct PDU injection
    * PDU injection into an existing connection, to the slave device
    * PDU injection into an existing connection, to the master device
    * Connection hijacking targeting the master
    * Connection hijacking targeting the slave 
	* Connection Man-in-the-Middle targeting initiation requests
    * Connection Man-in-the-Middle targeting an existing connection
    * Connection jamming
    * Advertisements jamming
    * Reactive jamming

* High-level capabilities
	* Scanner role: the device can listen for advertisements and report them
    * Advertiser role: the device can send advertisements
	* Central role: the device can act as a BLE Central device and initiate a connection
	* Peripheral role: the device can act as BLE Peripheral device and receive connections

#### 802.15.4 capabilities

* Low-level capabilities
	* Channel jamming
	* Reactive jamming
	* Packet injection with control of its FCS
    * Packet injection without control of its FCS
    * Packet sniffing
    * Man-in-the-middle attack

* High-level capabilities
	* End device role: device can join a ZigBee network and act as an end device
	* Coordinator role: device can act as a Coordinator and manages its own ZigBee network
	* Router role: device can act as a Router and relay packets

#### Enhanced ShockBurst capabilities

* Low-level capabilities
    * Channel jamming
	* Reactive jamming
	* Packet injection
	* Packet sniffing (any address)
    * Packet sniffing (targeting a specific address)

* High-level capabilities
	* PRX role: the device can listen for packets and send acks
	* PTX role: the device can send packets

#### PHY capabilities
* Low-level capabilities
	* Frequency selection
    * Modulation selection
    * Datarate selection
    * Preambule selection
    * Packet size selection
    * Raw packet sniffing
    * Raw packet injection
    * Channel activity monitoring

---

## What's different on the `clue` branch

This is the `XTheocharis/whad-protocol` fork (branch `clue`) tracking `upstream/whad-team/whad-protocol#main`. The branch adds a **9th protocol domain — Board** — and is the schema-first source for the synchronized CLUE feature across all four WHAD repos. 2 commits ahead of upstream/main; merge base is `c9244c7` (2026-01-23).

### Board domain (`whad/protocol/board/`)
- `board.proto` (200L) — **28 commands** (BoardCommand enum 0x00-0x1B, `GetBoardInfo` → `RawPcmDiagnostics`), **57 messages**, **15 enums** (RuntimeMode, ResourceKind, OutputTarget, InputMode/Source/Action, Gesture, GpioDirection/Pull, SpiMode, StorageState, BoardResultCode, SensorStatusFlag, BoardStatusCode). Resource leasing first-class via `LeaseToken{resource,instance,generation,owner}`. Top-level `Message` oneof has **49 fields**.
- `board.options` (29L) — nanopb field-size annotations capping strings at 32-96 chars, I2C/SPI buffers at 512B, audio PCM at 800B, log chunks at 900B, `RemoteProfile.mappings max_count:16`.
- `board_manifest.json` (105L) — machine-readable schema inventory: `domain=0x0C000000`, `encoded_message_limit=1019`, 28-entry `commands[]` table (each with `request`/`start`/`terminal`/`events`), 14-entry `sensors[]` table (canonical CLUE sensor inventory: ids 1-14 covering accel/gyro/mag/quaternion/Euler/pressure/temp/humidity/color/proximity/gesture/audio_level/air_mouse).
- `status` field marks the Board domain as `"project-local pending upstream approval"`.

### Discovery schema (`whad/protocol/`)
- `whad.proto` — top-level `Message` oneof gains slot **`board.Message board = 8`** (append-only; field numbers wire-stable).
- `device.proto` — `Domain.Board = 0x0C000000` + four new `Capability` bits: `Read=0x100`, `Write=0x200`, `Stream=0x400`, `Store=0x800` (Board-specific capability flags).

### Drift detector (`tools/validate_board_manifest.py`, NEW 280L)
PEP 723 inline script (`uv run --script`, dep `protobuf>=6.31.1`, py≥3.12). Three validation phases:
1. `validate_manifest` — regex-parses `board.proto` (no protobuf import) and asserts the BoardCommand enum, manifest commands[], oneof_tags, and 14-sensor table all match.
2. `validate_options` — finds every `bytes`/`string`/`repeated` field in `board.proto` and asserts each has a matching `max_size`/`max_count` in `board.options`.
3. `validate_encoded_sizes` — loads freshly-built `dist/python/*_pb2.py`, builds maximally-filled instances of every Board message variant, wraps in `whad.Message`, serializes, asserts none exceeds `encoded_message_limit=1019`.

Exits 1 on any drift. Run after `make`.

### Generated outputs (`dist/`, 25 files)
Regenerated by `make` (Python `*_pb2.py` for `whad-client` + nanopb `*.pb.{c,h}` for `whad-lib`/`butterfly`). One new `dist/python/whad/protocol/board/board_pb2.py` (182L) + one new `dist/nanopb/whad/protocol/board/board.{pb.c,pb.h}`; existing device/whad/ble/phy/etc outputs regenerated to pick up the new domain/capability enum members.

### CI
No workflow changes — this repo has no GitHub Actions.

### Forward references
Consumed by:
- `whad-lib` (C API via X-macro `WHAD_BOARD_MESSAGE_LIST`)
- `butterfly` firmware (board dispatcher `src/boardModule.cpp`)
- `whad-client` (Python hub wrappers `whad/hub/board/` + connector `whad/board/connector/base.py` + CLI `whad/tools/wboard.py`)

See workspace `README.md` for the integrated 4-repo picture and `TODO.md` for outstanding work.

