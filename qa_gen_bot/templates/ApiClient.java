package {{PACKAGE}}.client;

import {{PACKAGE}}.dto.request.{{DTO_INPUT}};
import io.restassured.response.Response;
import io.restassured.specification.RequestSpecification;

import static io.restassured.RestAssured.given;

/**
 * API client (scaffold). Instance methods — tests use new {{CLIENT_CLASS}}(requestSpec).
 */
public class {{CLIENT_CLASS}} {

    private final RequestSpecification spec;

    public {{CLIENT_CLASS}}(RequestSpecification spec) {
        this.spec = spec;
    }

    private static final String BASE = "/{{RESOURCE}}";

    public Response getAll() {
        return given()
                .spec(spec)
                .when()
                .get(BASE)
                .then()
                .extract()
                .response();
    }

    public Response getById({{ID_JAVA_TYPE}} {{ID_PARAM}}) {
        return given()
                .spec(spec)
                .when()
                .get(BASE + "{{ID_PATH_SUFFIX}}", {{ID_PARAM}})
                .then()
                .extract()
                .response();
    }

    public Response create({{DTO_INPUT}} body) {
        return given()
                .spec(spec)
                .body(body)
                .when()
                .post(BASE)
                .then()
                .extract()
                .response();
    }

    public Response update({{ID_JAVA_TYPE}} {{ID_PARAM}}, {{DTO_INPUT}} body) {
        return given()
                .spec(spec)
                .body(body)
                .when()
                .put(BASE + "{{ID_PATH_SUFFIX}}", {{ID_PARAM}})
                .then()
                .extract()
                .response();
    }

    public Response delete({{ID_JAVA_TYPE}} {{ID_PARAM}}) {
        return given()
                .spec(spec)
                .when()
                .delete(BASE + "{{ID_PATH_SUFFIX}}", {{ID_PARAM}})
                .then()
                .extract()
                .response();
    }
}
