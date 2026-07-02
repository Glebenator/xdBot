import asyncio

from utils.db_handler import DatabaseHandler


def test_quote_storage_lifecycle(tmp_path) -> None:
    async def run_test() -> None:
        handler = DatabaseHandler(str(tmp_path / "bot.db"))

        quote = await handler.add_quote(
            123,
            "this belongs in the hall",
            quoted_user_id=10,
            quoted_username="Quoted User",
            saved_by_user_id=20,
            saved_by_username="Saver",
            channel_id=30,
            message_id=40,
        )

        assert quote["id"] > 0
        assert quote["duplicate"] is False

        duplicate = await handler.add_quote(
            123,
            "this belongs in the hall",
            quoted_user_id=10,
            quoted_username="Quoted User",
            saved_by_user_id=21,
            saved_by_username="Second Saver",
            channel_id=30,
            message_id=40,
        )

        assert duplicate["id"] == quote["id"]
        assert duplicate["duplicate"] is True

        random_quote = await handler.get_random_quote(123)
        assert random_quote is not None
        assert random_quote["quote_text"] == "this belongs in the hall"

        user_quote = await handler.get_random_quote(123, quoted_user_id=10)
        assert user_quote is not None
        assert user_quote["quoted_username"] == "Quoted User"

        listed = await handler.list_quotes(123, limit=5)
        assert [row["id"] for row in listed] == [quote["id"]]

        assert await handler.delete_quote(123, quote["id"]) is True
        assert await handler.get_quote(123, quote["id"]) is None
        assert await handler.list_quotes(123) == []

    asyncio.run(run_test())
