"""OrderItem vs OrderItemDto alignment."""
from qa_gen_bot.structure_fixer import sync_component_dto_suffix


def test_promotes_order_item_to_order_item_dto():
    pkg = "com.demo"
    base_path = f"src/main/java/{pkg.replace('.', '/')}/dto/request/OrderItem.java"
    test_path = f"src/test/java/{pkg.replace('.', '/')}/tests/T.java"
    files = {
        base_path: f"package {pkg}.dto.request;\npublic class OrderItem {{}}\n",
        test_path: f"""
            package {pkg}.tests;
            import {pkg}.dto.request.OrderItemDto;
            class T {{ OrderItemDto x; }}
        """,
    }
    result = sync_component_dto_suffix(files)
    assert not any(p.endswith("OrderItem.java") for p in result.files)
    assert any(p.endswith("OrderItemDto.java") for p in result.files)
    assert "class OrderItemDto" in next(
        c for p, c in result.files.items() if p.endswith("OrderItemDto.java")
    )
