package {{PACKAGE}}.base;

import {{PACKAGE}}.config.ConfigManager;
import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import io.restassured.RestAssured;
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.filter.log.LogDetail;
import io.restassured.http.ContentType;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;

import static com.github.tomakehurst.wiremock.client.WireMock.configureFor;

public abstract class WireMockBaseTest {

    protected static final ConfigManager config = ConfigManager.getInstance();
    protected static WireMockServer wireMockServer;
    public static RequestSpecification wireMockSpec;

    @BeforeAll
    static void startWireMock() {
        wireMockServer = new WireMockServer(
                WireMockConfiguration.options()
                        .dynamicPort()
        );
        wireMockServer.start();
        configureFor("localhost", wireMockServer.port());

        wireMockSpec = new RequestSpecBuilder()
                .setBaseUri("http://localhost:" + wireMockServer.port())
                .setContentType(ContentType.JSON)
                .setAccept(ContentType.JSON)
                .log(LogDetail.ALL)
                .build();

        RestAssured.enableLoggingOfRequestAndResponseIfValidationFails();
    }

    @AfterAll
    static void stopWireMock() {
        if (wireMockServer != null) {
            wireMockServer.stop();
        }
    }
}
