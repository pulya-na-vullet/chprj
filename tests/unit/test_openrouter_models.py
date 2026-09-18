from neurolegal.rag.openrouter_models import parse_models_payload


def test_parse_models_payload_maps_fields():
    payload = {
        "data": [
            {
                "id": "qwen/qwen3.6-flash",
                "name": "Qwen3.6 Flash",
                "context_length": 131072,
                "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                "supported_parameters": ["tools", "temperature"],
            },
            {
                "id": "x/no-tools",
                "name": "No Tools",
                "context_length": 64000,
                "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
                "supported_parameters": ["temperature"],
            },
        ]
    }
    models = parse_models_payload(payload)
    assert models[0].id == "qwen/qwen3.6-flash"
    assert models[0].context_length == 131072
    assert models[0].prompt_price == "0.00000015"
    assert models[0].supports_tools is True
    assert models[1].supports_tools is False


def test_parse_models_payload_tolerates_missing_fields():
    models = parse_models_payload({"data": [{"id": "a/b"}]})
    assert models[0].id == "a/b"
    assert models[0].name == "a/b"
    assert models[0].context_length is None
    assert models[0].supports_tools is False
