"""Manifest-driven composite sprite engine and playable Pygame demo.

Install Pygame with ``python -m pip install pygame``, then run this file.
Real characters are discovered from JSON manifests in ``assets/``; built-in
placeholders keep the demo playable before any art is available.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Mapping

try:
    import pygame
except ImportError as exc:  # pragma: no cover - exercised only without Pygame
    raise SystemExit(
        "sprite_engine_v2.py requires Pygame. Install it with: "
        "python -m pip install pygame"
    ) from exc


WINDOW_SIZE = (960, 540)
GROUND_Y = 430
SCALE = 4


def application_root() -> Path:
    """Return the user-visible folder beside the script or packaged EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class State(IntEnum):
    IDLE = 0
    WALK = 1
    PUNCH = 2
    KICK = 3
    SLASH = 4
    THRUST = 5
    HURT = 6
    JUMP = 7
    CROUCH = 8
    GUARD = 9
    SPECIAL = 10


class Archetype(IntEnum):
    UNARMED = 0
    SWORD = 1
    TAIL = 2


STATE_NAMES = {state.name.lower(): state for state in State}
ARCHETYPES = {archetype.name.lower(): archetype for archetype in Archetype}
ATTACKS = {
    Archetype.UNARMED: (State.PUNCH, State.KICK),
    Archetype.SWORD: (State.SLASH, State.THRUST),
    Archetype.TAIL: (State.PUNCH, State.KICK),
}
NON_LOOPING = {
    State.PUNCH, State.KICK, State.SLASH, State.THRUST,
    State.HURT, State.JUMP, State.SPECIAL,
}


@dataclass(frozen=True)
class AnimationData:
    frames: tuple[pygame.Surface, ...]
    durations_ms: tuple[int, ...]
    loop: bool = True
    return_to: State = State.IDLE
    vfx_frames: tuple[pygame.Surface, ...] = ()
    vfx_offset: tuple[int, int] = (0, 0)
    hitbox_overrides: Mapping[int, Mapping[str, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class CharacterData:
    char_id: int
    name: str
    archetype: Archetype
    animations: Mapping[State, AnimationData]
    frame_size: tuple[int, int]
    palette: Mapping[str, str] = field(default_factory=dict)
    combo_routes: Mapping[tuple[State, State], State] = field(default_factory=dict)


def _hex_color(value: str) -> pygame.Color:
    return pygame.Color(value)


def _durations(value: int | list[int], count: int) -> tuple[int, ...]:
    if isinstance(value, int):
        return (max(1, value),) * count
    if len(value) != count:
        raise ValueError(f"duration_ms has {len(value)} values for {count} frames")
    return tuple(max(1, int(duration)) for duration in value)


def _slice_row(
    sheet: pygame.Surface,
    row: int,
    count: int,
    size: tuple[int, int],
) -> tuple[pygame.Surface, ...]:
    width, height = size
    frames = []
    for column in range(count):
        rect = pygame.Rect(column * width, row * height, width, height)
        if not sheet.get_rect().contains(rect):
            raise ValueError(f"frame rectangle {rect} lies outside sheet {sheet.get_size()}")
        frames.append(sheet.subsurface(rect).copy())
    return tuple(frames)


def _make_placeholder_frames(
    name: str,
    state: State,
    colors: tuple[str, str],
    size: tuple[int, int] = (48, 48),
    count: int = 4,
) -> tuple[pygame.Surface, ...]:
    frames = []
    for index in range(count):
        surface = pygame.Surface(size, pygame.SRCALPHA)
        bob = round(math.sin(index / count * math.tau) * 2)
        shadow = pygame.Rect(10, 40, 28, 5)
        pygame.draw.ellipse(surface, "#14182180", shadow)
        pygame.draw.circle(surface, colors[1], (24, 13 + bob), 7)
        pygame.draw.rect(surface, colors[0], (17, 20 + bob, 14, 17), border_radius=3)
        pygame.draw.line(surface, colors[1], (19, 34 + bob), (15, 43), 4)
        pygame.draw.line(surface, colors[1], (29, 34 + bob), (33, 43), 4)
        reach = 12 if state in {State.PUNCH, State.SLASH, State.THRUST} and index == 2 else 5
        pygame.draw.line(surface, colors[1], (30, 23 + bob), (30 + reach, 25 + bob), 4)
        if state is State.KICK and index == 2:
            pygame.draw.line(surface, colors[1], (27, 34 + bob), (43, 31), 5)
        if state is State.GUARD:
            pygame.draw.circle(surface, "#8ed8e8", (34, 25), 8, 2)
        if state is State.SPECIAL:
            pygame.draw.circle(surface, colors[0], (24, 25), 20 + index, 2)
        if state is State.HURT:
            surface.set_alpha(150 if index % 2 else 255)
        frames.append(surface)
    return tuple(frames)


class SpriteEngine:
    """Loads sprite assets and creates independent runtime instances."""

    def __init__(self, asset_dir: str | Path = "assets") -> None:
        self.asset_dir = Path(asset_dir)
        self.characters: dict[str, CharacterData] = {}
        self._next_id = 0

    def load_all(self) -> None:
        self.characters.clear()
        self._next_id = 0
        if self.asset_dir.exists():
            for manifest_path in sorted(self.asset_dir.glob("*.json")):
                try:
                    self.load_manifest(manifest_path)
                except (KeyError, TypeError, ValueError, pygame.error) as exc:
                    print(f"Skipping {manifest_path.name}: {exc}")
        placeholders = (
            ("Akaza", Archetype.UNARMED, ("#d93874", "#caa3d8")),
            ("Mahito", Archetype.UNARMED, ("#6b9ec9", "#dfc9bd")),
            ("Yuta", Archetype.SWORD, ("#202b3d", "#dbc3b4")),
            ("Hashira", Archetype.SWORD, ("#256b62", "#e0b99f")),
            ("Meruem", Archetype.TAIL, ("#3b7943", "#b7cf82")),
        )
        loaded = {name.casefold() for name in self.characters}
        for name, archetype, colors in placeholders:
            if name.casefold() not in loaded:
                self.register(self.make_placeholder(name, archetype, colors))

    def register(self, character: CharacterData) -> CharacterData:
        self.characters[character.name] = character
        self._next_id = max(self._next_id, character.char_id + 1)
        return character

    def load_manifest(self, manifest_path: str | Path) -> CharacterData:
        path = Path(manifest_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        name = str(raw.get("name") or path.stem.replace("_manifest", "").title())
        archetype = ARCHETYPES[str(raw["archetype"]).lower()]
        frame_size = tuple(int(value) for value in raw["frame_size"])
        if len(frame_size) != 2:
            raise ValueError("frame_size must contain width and height")
        sheet_name = raw.get("sheet", f"{path.stem.replace('_manifest', '')}.png")
        sheet = pygame.image.load(str(path.parent / sheet_name)).convert_alpha()
        animations: dict[State, AnimationData] = {}
        for state_name, spec in raw["animations"].items():
            state = STATE_NAMES[state_name.lower()]
            count = int(spec["frames"])
            frames = _slice_row(sheet, int(spec["row"]), count, frame_size)
            vfx_frames: tuple[pygame.Surface, ...] = ()
            if "vfx_row" in spec:
                vfx_size = tuple(int(value) for value in spec.get("vfx_size", frame_size))
                vfx_frames = _slice_row(sheet, int(spec["vfx_row"]), count, vfx_size)
            overrides = {
                int(index): {key: int(value) for key, value in override.items()}
                for index, override in spec.get("hitbox_overrides", {}).items()
            }
            animations[state] = AnimationData(
                frames=frames,
                durations_ms=_durations(spec.get("duration_ms", 100), count),
                loop=bool(spec.get("loop", state not in NON_LOOPING)),
                return_to=STATE_NAMES[str(spec.get("return_to", "idle")).lower()],
                vfx_frames=vfx_frames,
                vfx_offset=tuple(int(value) for value in spec.get("vfx_offset", (0, 0))),
                hitbox_overrides=overrides,
            )
        combo_routes = self._parse_combo_routes(raw.get("combo_routes", {}))
        character = CharacterData(
            int(raw.get("char_id", self._next_id)), name, archetype,
            animations, frame_size, raw.get("palette", {}), combo_routes,
        )
        return self.register(character)

    @staticmethod
    def _parse_combo_routes(raw: Mapping[str, str]) -> dict[tuple[State, State], State]:
        routes = {}
        for route, destination in raw.items():
            current, input_state = (part.strip().lower() for part in route.split("+", 1))
            routes[(STATE_NAMES[current], STATE_NAMES[input_state])] = STATE_NAMES[destination.lower()]
        return routes

    def make_placeholder(
        self,
        name: str,
        archetype: Archetype,
        colors: tuple[str, str],
    ) -> CharacterData:
        available_attacks = ATTACKS[archetype]
        states = (State.IDLE, State.WALK, *available_attacks, State.HURT,
                  State.JUMP, State.CROUCH, State.GUARD, State.SPECIAL)
        animations = {}
        for state in states:
            count = 2 if state in {State.HURT, State.JUMP, State.CROUCH, State.GUARD} else 4
            animations[state] = AnimationData(
                _make_placeholder_frames(name, state, colors, count=count),
                (150 if state is State.IDLE else 90,) * count,
                state not in NON_LOOPING,
                State.IDLE,
                hitbox_overrides={2: {"x_offset": 8, "w_override": 56}}
                if state in available_attacks else {},
            )
        routes = {
            (available_attacks[0], available_attacks[0]): available_attacks[1],
            (available_attacks[1], available_attacks[0]): State.SPECIAL,
        }
        return CharacterData(self._next_id, name, archetype, animations, (48, 48), {}, routes)

    def create(self, name: str, position: tuple[float, float]) -> "CompositeSprite":
        return CompositeSprite(self.characters[name], position)

    def generate_template_manifests(self) -> list[Path]:
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for sheet_path in sorted(self.asset_dir.glob("*.png")):
            manifest_path = sheet_path.with_suffix(".json")
            if manifest_path.exists():
                continue
            manifest = self._template_manifest(sheet_path.stem, sheet_path.name)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            written.append(manifest_path)
        return written

    def export_debug_pngs(self, output_dir: str | Path = "debug_png") -> list[Path]:
        """Export transparent frames and one labeled contact sheet per character."""
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        pygame.font.init()
        label_font = pygame.font.Font(None, 18)
        written: list[Path] = []
        for character in self.characters.values():
            actor = CompositeSprite(character, (0, 0))
            rendered: list[tuple[State, list[pygame.Surface]]] = []
            character_dir = destination / self._file_slug(character.name)
            character_dir.mkdir(parents=True, exist_ok=True)
            for state, animation in character.animations.items():
                state_frames = []
                for frame_idx in range(len(animation.frames)):
                    frame = actor.render_frame(state, frame_idx)
                    frame_path = character_dir / f"{state.name.lower()}_{frame_idx:02d}.png"
                    pygame.image.save(frame, str(frame_path))
                    written.append(frame_path)
                    state_frames.append(frame)
                rendered.append((state, state_frames))
            review_path = destination / f"{self._file_slug(character.name)}_review.png"
            pygame.image.save(self._make_contact_sheet(character.name, rendered, label_font), str(review_path))
            written.append(review_path)
        return written

    @staticmethod
    def _file_slug(value: str) -> str:
        return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")

    @staticmethod
    def _make_contact_sheet(
        name: str,
        rendered: list[tuple[State, list[pygame.Surface]]],
        font: pygame.font.Font,
    ) -> pygame.Surface:
        frames = [frame for _, state_frames in rendered for frame in state_frames]
        frame_width = max(frame.get_width() for frame in frames)
        frame_height = max(frame.get_height() for frame in frames)
        columns = max(len(state_frames) for _, state_frames in rendered)
        label_width = 88
        header_height = 34
        cell_width = frame_width + 12
        cell_height = frame_height + 12
        sheet = pygame.Surface(
            (label_width + columns * cell_width, header_height + len(rendered) * cell_height)
        )
        sheet.fill("#151a21")
        sheet.blit(font.render(f"{name} - composite frame review", True, "#f4eee5"), (8, 9))
        checker = 12
        for row, (state, state_frames) in enumerate(rendered):
            top = header_height + row * cell_height
            sheet.blit(font.render(state.name.lower(), True, "#b9c7d5"), (8, top + 8))
            for column in range(columns):
                left = label_width + column * cell_width
                for y in range(top, top + cell_height, checker):
                    for x in range(left, left + cell_width, checker):
                        color = "#d5d9dd" if (x // checker + y // checker) % 2 else "#aeb4bb"
                        pygame.draw.rect(sheet, color, (x, y, checker, checker))
                if column < len(state_frames):
                    frame = state_frames[column]
                    frame_rect = frame.get_rect(center=(left + cell_width // 2, top + cell_height // 2))
                    sheet.blit(frame, frame_rect)
        return sheet

    @staticmethod
    def _template_manifest(name: str, sheet: str) -> dict[str, Any]:
        archetype = "tail" if "meruem" in name.lower() else "sword" if any(
            word in name.lower() for word in ("yuta", "hashira", "sword")
        ) else "unarmed"
        attacks = ("slash", "thrust") if archetype == "sword" else ("punch", "kick")
        states = ["idle", "walk", *attacks, "hurt", "jump", "crouch", "guard", "special"]
        animations = {}
        for row, state in enumerate(states):
            count = 2 if state in {"hurt", "jump", "crouch", "guard"} else 4
            animations[state] = {
                "row": row, "frames": count,
                "duration_ms": 150 if state == "idle" else 100,
                "loop": state not in {"punch", "kick", "slash", "thrust", "hurt", "jump", "special"},
            }
            if not animations[state]["loop"]:
                animations[state]["return_to"] = "idle"
        return {
            "name": name.replace("_", " ").title(), "archetype": archetype,
            "sheet": sheet, "frame_size": [48, 48], "palette": {},
            "animations": animations,
            "combo_routes": {f"{attacks[0]}+{attacks[0]}": attacks[1]},
        }

    @staticmethod
    def palette_swap(
        source: pygame.Surface,
        color_map: Mapping[str | tuple[int, int, int], str | tuple[int, int, int]],
    ) -> pygame.Surface:
        result = source.copy()
        pixels = pygame.PixelArray(result)
        try:
            for old, new in color_map.items():
                old_color = _hex_color(old) if isinstance(old, str) else pygame.Color(*old)
                new_color = _hex_color(new) if isinstance(new, str) else pygame.Color(*new)
                pixels.replace(old_color, new_color, distance=0)
        finally:
            del pixels
        return result


class CompositeSprite(pygame.sprite.Sprite):
    """Runtime state, physics, input buffering, and layered composition."""

    def __init__(self, data: CharacterData, position: tuple[float, float]) -> None:
        super().__init__()
        self.data = data
        self.position = pygame.Vector2(position)
        self.velocity = pygame.Vector2()
        self.state = State.IDLE
        self.frame_idx = 0
        self.frame_elapsed_ms = 0.0
        self.facing = 1
        self.grounded = True
        self._buffered_attack: State | None = None
        self.image = pygame.Surface(data.frame_size, pygame.SRCALPHA)
        self.rect = self.image.get_rect(midbottom=(round(self.position.x), round(self.position.y)))
        self._rika_frames = self._make_rika_frames() if data.name.casefold() == "yuta" else ()
        self._compose()

    @property
    def animation(self) -> AnimationData:
        return self.data.animations[self.state]

    @property
    def hitbox(self) -> pygame.Rect:
        box = self.rect.inflate(-self.rect.width // 3, -self.rect.height // 5)
        override = self.animation.hitbox_overrides.get(self.frame_idx, {})
        width = override.get("w_override", box.width) * SCALE
        x_offset = override.get("x_offset", 0) * SCALE * self.facing
        box.width = width
        box.centerx = self.rect.centerx + x_offset
        return box

    def set_state(self, state: State, force: bool = False) -> bool:
        if state not in self.data.animations:
            return False
        if self.state is State.HURT and state is not State.IDLE and not force:
            return False
        if self.state in NON_LOOPING and state not in {State.HURT, State.IDLE} and not force:
            route = self.data.combo_routes.get((self.state, state))
            if route is not None:
                self._buffered_attack = route
                return True
            return False
        if state is self.state:
            return True
        self.state = state
        self.frame_idx = 0
        self.frame_elapsed_ms = 0.0
        self._buffered_attack = None
        return True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        primary, secondary = ATTACKS[self.data.archetype]
        actions = {
            pygame.K_z: primary, pygame.K_x: secondary,
            pygame.K_c: State.SPECIAL, pygame.K_DOWN: State.CROUCH,
            pygame.K_LSHIFT: State.GUARD, pygame.K_RSHIFT: State.GUARD,
        }
        if event.key == pygame.K_UP and self.grounded:
            if self.set_state(State.JUMP):
                self.velocity.y = -430
                self.grounded = False
        elif event.key in actions:
            self.set_state(actions[event.key])

    def handle_input(self, keys: pygame.key.ScancodeWrapper) -> None:
        direction = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        self.velocity.x = direction * 180
        if direction:
            self.facing = direction
            if self.grounded and self.state in {State.IDLE, State.WALK}:
                self.set_state(State.WALK)
        elif self.grounded and self.state is State.WALK:
            self.set_state(State.IDLE)
        if self.grounded and self.state in {State.CROUCH, State.GUARD}:
            held = keys[pygame.K_DOWN] if self.state is State.CROUCH else (
                keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
            )
            if not held:
                self.set_state(State.IDLE)

    def update(self, delta_ms: float) -> None:
        delta_seconds = delta_ms / 1000
        self.position.x += self.velocity.x * delta_seconds
        if not self.grounded:
            self.velocity.y += 980 * delta_seconds
            self.position.y += self.velocity.y * delta_seconds
            if self.position.y >= GROUND_Y:
                self.position.y = GROUND_Y
                self.velocity.y = 0
                self.grounded = True
                self.set_state(State.IDLE, force=True)
        self.position.x = max(40, min(WINDOW_SIZE[0] - 40, self.position.x))
        self._advance_animation(delta_ms)
        self._compose()
        self.rect = self.image.get_rect(midbottom=(round(self.position.x), round(self.position.y)))

    def render_frame(self, state: State, frame_idx: int, facing: int = 1) -> pygame.Surface:
        """Render one gameplay-accurate composite frame for tools and previews."""
        if state not in self.data.animations:
            raise ValueError(f"{self.data.name} has no {state.name.lower()} animation")
        animation = self.data.animations[state]
        if not 0 <= frame_idx < len(animation.frames):
            raise IndexError(f"frame {frame_idx} is outside {state.name.lower()}")
        self.state = state
        self.frame_idx = frame_idx
        self.facing = 1 if facing >= 0 else -1
        self._compose()
        return self.image.copy()

    def _advance_animation(self, delta_ms: float) -> None:
        self.frame_elapsed_ms += delta_ms
        while self.frame_elapsed_ms >= self.animation.durations_ms[self.frame_idx]:
            self.frame_elapsed_ms -= self.animation.durations_ms[self.frame_idx]
            if self.frame_idx + 1 < len(self.animation.frames):
                self.frame_idx += 1
                continue
            if self.animation.loop:
                self.frame_idx = 0
                continue
            next_state = self._buffered_attack or self.animation.return_to
            self.set_state(next_state, force=True)
            break

    def _compose(self) -> None:
        animation = self.animation
        layers: list[tuple[pygame.Surface, tuple[int, int]]] = []
        body = animation.frames[self.frame_idx]
        if self.data.archetype is Archetype.TAIL:
            tail = pygame.Surface(self.data.frame_size, pygame.SRCALPHA)
            pygame.draw.arc(tail, "#9fcf73", (3, 17, 31, 27), 1.8, 5.2, 4)
            layers.append((tail, (0, 0)))
        layers.append((body, (0, 0)))
        if animation.vfx_frames:
            layers.append((animation.vfx_frames[self.frame_idx], animation.vfx_offset))
        if self._rika_frames and self.state is State.SPECIAL:
            layers.append((self._rika_frames[self.frame_idx % len(self._rika_frames)], (-8, -16)))
        min_x = min(offset[0] for _, offset in layers)
        min_y = min(offset[1] for _, offset in layers)
        max_x = max(surface.get_width() + offset[0] for surface, offset in layers)
        max_y = max(surface.get_height() + offset[1] for surface, offset in layers)
        composite = pygame.Surface((max_x - min_x, max_y - min_y), pygame.SRCALPHA)
        for surface, offset in layers:
            layer = pygame.transform.flip(surface, True, False) if self.facing < 0 else surface
            x = offset[0] - min_x
            if self.facing < 0:
                x = composite.get_width() - layer.get_width() - x
            composite.blit(layer, (x, offset[1] - min_y))
        self.image = pygame.transform.scale_by(composite, SCALE)

    @staticmethod
    def _make_rika_frames() -> tuple[pygame.Surface, ...]:
        frames = []
        for index in range(4):
            frame = pygame.Surface((64, 64), pygame.SRCALPHA)
            frame.set_alpha(95 + index * 25)
            pygame.draw.ellipse(frame, "#aeb9d9", (10, 7 - index, 44, 50 + index * 2))
            pygame.draw.circle(frame, "#111927", (25, 25), 3)
            pygame.draw.circle(frame, "#111927", (39, 25), 3)
            pygame.draw.arc(frame, "#111927", (22, 25, 20, 16), 0.1, 3.0, 2)
            frames.append(frame)
        return tuple(frames)

    def serialize(self) -> bytes:
        return struct.pack(
            "<BBBbff", self.data.char_id, int(self.state), self.frame_idx,
            self.facing, self.position.x, self.position.y,
        )

    def apply_network_state(self, packet: bytes) -> int:
        char_id, state, frame_idx, facing, x, y = struct.unpack("<BBBbff", packet)
        self.state = State(state)
        self.frame_idx = min(frame_idx, len(self.animation.frames) - 1)
        self.facing = 1 if facing >= 0 else -1
        self.position.update(x, y)
        self.frame_elapsed_ms = 0
        return char_id


def run_demo() -> None:
    pygame.init()
    pygame.display.set_caption("Composite Sprite Engine v2")
    screen = pygame.display.set_mode(WINDOW_SIZE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 28)
    small_font = pygame.font.Font(None, 21)
    root = application_root()
    engine = SpriteEngine(root / "assets")
    engine.load_all()
    roster = list(engine.characters)
    roster_index = 0
    actor = engine.create(roster[roster_index], (WINDOW_SIZE[0] / 2, GROUND_Y))
    notice = ""
    notice_until = 0
    running = True
    while running:
        delta_ms = min(clock.tick(60), 50)
        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                roster_index = (roster_index + 1) % len(roster)
                actor = engine.create(roster[roster_index], (actor.position.x, GROUND_Y))
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                written = engine.generate_template_manifests()
                notice = f"Generated {len(written)} manifest(s) in assets/"
                notice_until = pygame.time.get_ticks() + 2500
                print(notice, *(path.name for path in written))
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                debug_dir = root / "debug_png"
                written = engine.export_debug_pngs(debug_dir)
                notice = f"Exported {len(written)} PNGs to debug_png/"
                notice_until = pygame.time.get_ticks() + 2500
                print(notice)
            else:
                actor.handle_event(event)
        actor.handle_input(pygame.key.get_pressed())
        actor.update(delta_ms)
        screen.fill("#131820")
        pygame.draw.rect(screen, "#202833", (0, GROUND_Y, WINDOW_SIZE[0], WINDOW_SIZE[1] - GROUND_Y))
        pygame.draw.line(screen, "#516070", (0, GROUND_Y), (WINDOW_SIZE[0], GROUND_Y), 2)
        screen.blit(actor.image, actor.rect)
        title = font.render(f"{actor.data.name}  |  {actor.data.archetype.name.lower()}  |  {actor.state.name.lower()}", True, "#f2eadf")
        help_text = small_font.render(
            "Arrows move/jump/crouch   Z/X attack   C special   Shift guard   Tab character   P export   G manifests",
            True, "#aab7c4",
        )
        screen.blit(title, (24, 20))
        screen.blit(help_text, (24, 52))
        if notice and pygame.time.get_ticks() < notice_until:
            notice_text = small_font.render(notice, True, "#f2c96d")
            screen.blit(notice_text, (24, 80))
        pygame.display.flip()
    pygame.quit()


def run_smoke_test() -> None:
    """Exercise the packaged runtime without opening a visible window."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    pygame.display.set_mode((1, 1))
    engine = SpriteEngine(application_root() / "__smoke_test_assets__")
    engine.load_all()
    expected = {"Akaza", "Mahito", "Yuta", "Hashira", "Meruem"}
    if set(engine.characters) != expected:
        raise RuntimeError(f"unexpected roster: {sorted(engine.characters)}")
    actor = engine.create("Akaza", (480, GROUND_Y))
    if len(actor.serialize()) != 12:
        raise RuntimeError("network packet is not 12 bytes")
    actor.set_state(State.PUNCH)
    actor.set_state(State.PUNCH)
    actor.update(1000)
    if actor.state is not State.KICK:
        raise RuntimeError("buffered combo did not reach kick")
    print("Sprite engine smoke test passed: 5 characters, combo OK, packet=12 bytes")
    pygame.quit()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Crusader composite sprite engine")
    parser.add_argument("--smoke-test", action="store_true", help="run headless self-test and exit")
    parser.add_argument("--export-debug", action="store_true", help="export review PNGs and exit")
    args = parser.parse_args(argv)
    if args.smoke_test:
        run_smoke_test()
        return
    if args.export_debug:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.init()
        pygame.display.set_mode((1, 1))
        root = application_root()
        engine = SpriteEngine(root / "assets")
        engine.load_all()
        written = engine.export_debug_pngs(root / "debug_png")
        print(f"Exported {len(written)} PNGs to {root / 'debug_png'}")
        pygame.quit()
        return
    run_demo()


if __name__ == "__main__":
    main()