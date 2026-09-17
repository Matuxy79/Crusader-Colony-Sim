from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

from sprite_engine_v2 import GROUND_Y, SpriteEngine, State


class SpriteEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_engine(self) -> SpriteEngine:
        engine = SpriteEngine(Path("__test_assets_do_not_exist__"))
        engine.load_all()
        return engine

    def test_roster_combo_and_network_packet(self) -> None:
        engine = self.make_engine()
        self.assertEqual(set(engine.characters), {"Akaza", "Mahito", "Yuta", "Hashira", "Meruem"})
        actor = engine.create("Akaza", (480, GROUND_Y))
        actor.set_state(State.PUNCH)
        actor.set_state(State.PUNCH)
        actor.update(1000)
        self.assertIs(actor.state, State.KICK)
        packet = actor.serialize()
        self.assertEqual(len(packet), 12)
        clone = engine.create("Akaza", (0, GROUND_Y))
        self.assertEqual(clone.apply_network_state(packet), actor.data.char_id)
        self.assertEqual(clone.state, actor.state)
        self.assertEqual(clone.position, actor.position)

    def test_debug_export(self) -> None:
        engine = self.make_engine()
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            written = engine.export_debug_pngs(output)
            reviews = [path for path in written if path.name.endswith("_review.png")]
            self.assertEqual(len(written), 145)
            self.assertEqual(len(reviews), 5)
            self.assertTrue(all(path.exists() for path in written))
            self.assertEqual(pygame.image.load(output / "akaza" / "idle_00.png").get_size(), (192, 192))
            self.assertEqual(pygame.image.load(output / "yuta" / "special_00.png").get_size(), (256, 256))


if __name__ == "__main__":
    unittest.main()