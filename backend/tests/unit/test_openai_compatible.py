from tess_chat.adapters.llm.openai_compatible import _message
from tess_chat.application.ports.llm import ChatTurn, ImagePart, TextPart


def test_text_only_parts_are_sent_as_a_plain_string() -> None:
    turn = ChatTurn("user", [TextPart("question"), TextPart("[Attached document: a.pdf]\nbody")])
    assert _message(turn)["content"] == "question\n[Attached document: a.pdf]\nbody"


def test_images_are_sent_as_content_parts() -> None:
    turn = ChatTurn("user", [TextPart("what is this"), ImagePart("image/png", "AAAA")])
    content = _message(turn)["content"]
    assert content[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
