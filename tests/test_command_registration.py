import asyncio
import importlib
from typing import Any

import main
from utils.db_handler import DatabaseHandler


class FakeFaceMesh:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def close(self) -> None:
        pass


class FakeFaceMeshModule:
    FaceMesh = FakeFaceMesh


class FakeWordFilter:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.bad_words: set[str] = set()

    def add_word(self, word: str) -> bool:
        word = word.lower()
        if word in self.bad_words:
            return False
        self.bad_words.add(word)
        return True

    def remove_word(self, word: str) -> bool:
        word = word.lower()
        if word not in self.bad_words:
            return False
        self.bad_words.remove(word)
        return True

    def check_message(self, message: str) -> list[str]:
        words = set(message.lower().split())
        return sorted(self.bad_words.intersection(words))


def _patch_startup_dependencies(monkeypatch, tmp_path) -> None:
    db = DatabaseHandler(str(tmp_path / "bot.db"))

    import utils.db_handler as db_handler

    monkeypatch.setattr(db_handler, "get_database_handler", lambda: db)

    for module_name in (
        "cogs.admin",
        "cogs.fun",
        "cogs.llm",
        "cogs.moderation",
        "cogs.music",
        "cogs.quotes",
    ):
        module = importlib.import_module(module_name)
        if hasattr(module, "get_database_handler"):
            monkeypatch.setattr(module, "get_database_handler", lambda: db)

    import mediapipe as mp

    solutions = getattr(mp, "solutions", None)
    face_mesh = getattr(solutions, "face_mesh", None) if solutions else None
    if face_mesh is not None:
        monkeypatch.setattr(face_mesh, "FaceMesh", FakeFaceMesh)

    from mediapipe.python.solutions import face_mesh as legacy_face_mesh

    monkeypatch.setattr(legacy_face_mesh, "FaceMesh", FakeFaceMesh)

    moderation_cog = importlib.import_module("cogs.moderation")
    monkeypatch.setattr(moderation_cog, "WordFilter", FakeWordFilter)


def test_all_discovered_cogs_load_together(monkeypatch, tmp_path) -> None:
    async def run_test() -> None:
        _patch_startup_dependencies(monkeypatch, tmp_path)

        bot = main.DiscordBot()
        extensions = sorted(main._iter_extension_paths("cogs"))

        try:
            for extension in extensions:
                await bot.load_extension(extension)

            assert sorted(bot.extensions) == extensions

            quote = bot.get_command("quote")
            stock = bot.get_command("stock")
            stockquote = bot.get_command("stockquote")
            price = bot.get_command("price")

            assert quote is not None
            assert quote.cog_name == "Quotes"
            assert stock is not None
            assert stock.cog_name == "Stocks"
            assert stockquote is stock
            assert price is stock
        finally:
            for extension in list(bot.extensions):
                await bot.unload_extension(extension)
            await bot.close()

    asyncio.run(run_test())


def test_image_cog_face_mesh_loader_falls_back_without_top_level_solutions(monkeypatch) -> None:
    image_cog = importlib.import_module("cogs.image")

    class MediaPipeWithoutSolutions:
        pass

    monkeypatch.setattr(image_cog, "mp", MediaPipeWithoutSolutions())

    face_mesh_module = image_cog._load_face_mesh_module()

    assert hasattr(face_mesh_module, "FaceMesh")
