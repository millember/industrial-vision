from app.main import create_app
from app.presentation import schemas
from app.presentation.openapi import OPERATIONS, SCHEMA_EXAMPLES


def test_openapi_operations_have_russian_guide_examples_and_security():
    app = create_app()
    schema = app.openapi()
    documented = {(method,path) for path,item in schema["paths"].items() for method in item}
    assert documented == set(OPERATIONS)
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            assert operation["tags"] and operation["tags"] != ["default"]
            assert operation["summary"] and len(operation["description"]) > 40
            for parameter in operation.get("parameters", []):
                assert parameter["description"]
            media = operation.get("requestBody", {}).get("content", {}).get("application/json")
            if media:
                assert media["examples"], (method,path)
            for code, response in operation["responses"].items():
                assert response["description"]
                if code == "204":
                    assert "content" not in response
                elif "/photos/" not in path or code != "200":
                    assert response["content"]["application/json"].get("examples"), (method,path,code)
    assert schema["paths"]["/api/v1/users"]["get"]["security"] == [{"AdminSession":[]}]
    assert schema["paths"]["/api/v1/me"]["get"]["security"] == [{"AccessToken":[]},{"AdminSession":[]}]
    assert not schema["paths"]["/api/v1/auth/token"]["post"].get("security")
    assert schema["components"]["securitySchemes"]["AdminSession"]["in"] == "cookie"
    assert app.openapi() is schema


def test_documented_schema_examples_pass_real_http_validation():
    for name, value in SCHEMA_EXAMPLES.items():
        model = getattr(schemas, name)
        model.model_validate(value)
    schema = create_app().openapi()
    for path,item in schema["paths"].items():
        for method, operation in item.items():
            for response in operation["responses"].values():
                media = response.get("content", {}).get("application/json", {})
                name = media.get("schema", {}).get("$ref", "").rsplit("/", 1)[-1]
                if hasattr(schemas, name):
                    for example in media.get("examples", {}).values():
                        getattr(schemas, name).model_validate(example["value"])
    request = schema["paths"]["/api/v1/inspections"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert request["properties"]["image"]["format"] == "binary"
    assert "EXIF" in request["properties"]["image"]["description"]
    assert set(schema["paths"]["/api/v1/photos/{photo_id}"]["get"]["responses"]["200"]["content"]) == {"image/jpeg","image/png"}


def test_openapi_references_resolve():
    schema = create_app().openapi()
    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                target = schema
                for part in value["$ref"].removeprefix("#/").split("/"):
                    target = target[part]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
