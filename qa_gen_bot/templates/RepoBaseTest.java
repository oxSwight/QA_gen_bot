package {{PACKAGE}}.base;

import {{PACKAGE}}.api.DefaultApi;
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.http.ContentType;

/**
 * Mode B: helpers for openapi-generator DefaultApi (fluent Oper API).
 */
public abstract class RepoBaseTest extends BaseTest {

    protected DefaultApi api() {
        return DefaultApi._default(() -> new RequestSpecBuilder()
                .setBaseUri(config.getBaseUrl())
                .setContentType(ContentType.JSON)
                .setAccept(ContentType.JSON));
    }
}
