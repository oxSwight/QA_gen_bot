package {{PACKAGE}}.base;

import {{PACKAGE}}.api.DefaultApi;
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.http.ContentType;

/**
 * Mode B: WireMock + openapi-generator DefaultApi.
 */
public abstract class RepoWireMockBaseTest extends WireMockBaseTest {

    protected DefaultApi api() {
        return DefaultApi._default(() -> new RequestSpecBuilder()
                .setBaseUri("http://localhost:" + wireMockServer.port())
                .setContentType(ContentType.JSON)
                .setAccept(ContentType.JSON));
    }
}
