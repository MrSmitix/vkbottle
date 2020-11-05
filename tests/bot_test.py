from vkbottle import Bot, API, GroupTypes, GroupEventType
from vkbottle.bot import Message, rules
from vkbottle.tools.test_utils import with_mocked_api, MockedClient
from vkbottle.tools.dev_tools import message_min
import pytest
import vbml
import typing
import json

EXAMPLE_EVENT = {
    "ts": 1,
    "updates": [
        {
            "type": "wall_post_new",
            "object": {
                "id": 28,
                "from_id": -123456,
                "owner_id": -123456,
                "date": 1519631591,
                "marked_as_ads": 0,
                "post_type": "post",
                "text": "Post text",
                "can_edit": 1,
                "created_by": 564321,
                "can_delete": 1,
                "comments": {"count": 0},
            },
            "group_id": 123456,
        },
        {
            "type": "message_new",
            "object": {
                "client_info": {
                    "button_actions": [
                        "text",
                        "vkpay",
                        "open_app",
                        "location",
                        "open_link",
                        "callback",
                    ],
                    "keyboard": True,
                    "inline_keyboard": True,
                    "carousel": False,
                    "lang_id": 0,
                },
                "message": {"id": 100, "from_id": 1,},
            },
        },
    ],
}


def set_http_callback(api: API, callback: typing.Callable[[dict], typing.Any]):
    api.http._session = MockedClient(callback=callback)


@pytest.mark.asyncio
async def test_bot_polling():
    def callback(data: dict):
        if "groups.getById" in data["url"]:
            return {"response": [{"id": 1}]}
        elif "groups.getLongPollServer" in data["url"]:
            return {"response": {"ts": 1, "server": "!SERVER!", "key": ""}}
        elif "!SERVER!" in data["url"]:
            return EXAMPLE_EVENT
        elif "messages.send" in data["url"]:
            return json.dumps({"response": 100})

    bot = Bot("token")
    set_http_callback(bot.api, callback)

    @bot.labeler.raw_event(GroupEventType.WALL_POST_NEW, GroupTypes.WallPostNew)
    async def wall_post_handler(post: GroupTypes.WallPostNew):
        assert post.object.owner_id == -123456
        assert post.ctx_api == bot.api

    @bot.labeler.message()
    async def message_handler(message: Message):
        assert message.id == 100
        assert message.from_id == 1
        assert await message.answer() == 100

    async for event in bot.polling.listen():
        assert event.get("updates")
        for update in event["updates"]:
            await bot.router.route(update, bot.api)
        break


@pytest.mark.asyncio
async def test_bot_scopes():
    bot = Bot(token="some token")
    assert bot.api.token == "some token"
    assert bot.api == bot.polling.api
    assert bot.labeler.message_view is bot.router.views["message"]
    assert bot.labeler.raw_event_view is bot.router.views["raw"]


def fake_message(ctx_api: API, **data: typing.Any) -> Message:
    return message_min(
        {
            "object": {
                "message": data,
                "client_info": data.get(
                    "client_info", EXAMPLE_EVENT["updates"][1]["object"]["client_info"]
                ),
            }
        },
        ctx_api,
    )


@pytest.mark.asyncio
@with_mocked_api(None)
async def test_rules(api: API):
    assert await rules.FromPeerRule(123).check(fake_message(api, peer_id=123))
    assert not await rules.FromUserRule().check(fake_message(api, from_id=-1))
    assert await rules.VBMLRule("i am in love with <whom>", vbml.Patcher()).check(
        fake_message(api, text="i am in love with you")
    ) == {"whom": "you"}
    assert await rules.FuncRule(lambda m: m.text.endswith("!")).check(
        fake_message(api, text="yes!")
    )
    assert not await rules.PeerRule(from_chat=True).check(fake_message(api, peer_id=1, from_id=1))
    assert await rules.PayloadMapRule([("a", int), ("b", str)]).check(
        fake_message(api, payload=json.dumps({"a": 1, "b": ""}))
    )
    assert await rules.StickerRule(sticker_ids=[1, 2]).check(
        fake_message(api, attachments=[{"type": "sticker", "sticker": {"sticker_id": 2}}])
    )
