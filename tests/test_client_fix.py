from qa_gen_bot.structure_fixer import _fix_client_file


def test_fix_client_does_not_break_field_declaration():
    pkg = "com.microserviceautomationap"
    broken = """
package com.microserviceautomationap.client;
import io.restassured.specification.RequestSpecification;
public class ProductsApiClient {
    private final RequestSpecification com.microserviceautomationap.base.BaseTest.requestSpec;
    public Response getAll() {
        return given().spec(requestSpec).when().get("/x").then().extract().response();
    }
}
"""
    fixed = _fix_client_file(broken, pkg)
    assert "RequestSpecification com.microserviceautomationap.base" not in fixed
    assert ".spec(com.microserviceautomationap.base.BaseTest.requestSpec)" in fixed
