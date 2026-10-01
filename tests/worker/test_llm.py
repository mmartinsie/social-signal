"""The LLM client: what it sends to llama.cpp's server and how it reads the
answers. The server is replaced by an httpx.MockTransport."""

import json

import httpx
import pytest

from socialsignal_worker import llm
from socialsignal_worker.summary import Counts


def client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://llm.test", transport=httpx.MockTransport(handler))


def answer(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_ready_only_when_health_answers_200():
    assert llm.is_ready(client(lambda request: httpx.Response(200, json={"status": "ok"})))
    assert not llm.is_ready(client(lambda request: httpx.Response(503)))


def test_not_ready_when_the_server_is_down():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    assert not llm.is_ready(client(refuse))


def test_model_name_is_the_served_alias():
    models = {"object": "list", "data": [{"id": "gemma-4-E2B-it-qat-q4_0"}]}

    assert llm.model_name(client(lambda request: httpx.Response(200, json=models))) == (
        "gemma-4-E2B-it-qat-q4_0"
    )


def test_classify_sends_the_schema_and_reads_the_label():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return answer('{"label": "negative"}')

    assert llm.classify(client(handler), "Worst update ever.", timeout=30) == "negative"
    body = sent[0]
    assert body["temperature"] == 0
    assert body["messages"][0] == {"role": "system", "content": llm.CLASSIFY_PROMPT}
    assert body["messages"][1] == {"role": "user", "content": "Worst update ever."}
    # OpenAI's shape, the one llama-server v0.5.0 enforces (D22).
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["properties"]["label"]["enum"] == [
        "positive",
        "neutral",
        "negative",
    ]


@pytest.mark.parametrize("content", ['{"label": "mixed"}', "positive", '{"sentiment": "positive"}'])
def test_anything_but_a_label_is_a_bad_answer(content):
    with pytest.raises(llm.BadAnswer):
        llm.classify(client(lambda request: answer(content)), "text", timeout=30)


def test_an_http_error_is_a_bad_answer():
    with pytest.raises(llm.BadAnswer, match="400"):
        llm.classify(client(lambda request: httpx.Response(400, text="too long")), "t", timeout=30)


def test_loading_means_unavailable():
    with pytest.raises(llm.Unavailable, match="503"):
        llm.classify(client(lambda request: httpx.Response(503)), "text", timeout=30)


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_down_or_too_slow_means_unavailable(error):
    def handler(request):
        raise error

    with pytest.raises(llm.Unavailable):
        llm.classify(client(handler), "text", timeout=30)


def test_sentence_prompt_has_the_counts_and_the_cut_posts():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return answer("  Mostly neutral posts\nabout Python releases.  ")

    sentence = llm.write_sentence(
        client(handler),
        "#python",
        Counts(positive=2, neutral=7, negative=1),
        "neutral",
        ["first post", "second\npost " + "x" * 50],
        post_chars=20,
        timeout=90,
    )

    assert sentence == "Mostly neutral posts about Python releases."
    body = sent[0]
    assert "response_format" not in body
    assert body["messages"][0]["content"] == llm.SENTENCE_PROMPT
    user = body["messages"][1]["content"]
    assert "Subscription: #python" in user
    assert "10 recent posts: 2 positive, 7 neutral, 1 negative (overall: neutral)" in user
    assert "The 2 most recent posts" in user
    # One line per post, each cut to post_chars (20) characters.
    assert user.endswith("\n- first post\n- second post " + "x" * 8)


def test_an_empty_sentence_is_a_bad_answer():
    with pytest.raises(llm.BadAnswer):
        llm.write_sentence(
            client(lambda request: answer("  \n ")),
            "#python",
            Counts(neutral=1),
            "neutral",
            ["a post"],
            post_chars=280,
            timeout=90,
        )
