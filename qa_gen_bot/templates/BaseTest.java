package {{PACKAGE}}.base;

import {{PACKAGE}}.config.ConfigManager;
import io.restassured.RestAssured;
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.builder.ResponseSpecBuilder;
import io.restassured.config.HttpClientConfig;
import io.restassured.config.RestAssuredConfig;
import io.restassured.filter.log.LogDetail;
import io.restassured.http.ContentType;
import io.restassured.specification.RequestSpecification;
import io.restassured.specification.ResponseSpecification;
import org.apache.http.params.CoreConnectionPNames;
import org.junit.jupiter.api.BeforeAll;

public abstract class BaseTest {

    protected static final ConfigManager config = ConfigManager.getInstance();
    public static RequestSpecification requestSpec;
    public static ResponseSpecification responseSpec;

    @BeforeAll
    static void configureRestAssured() {
        int connectionTimeout = config.getConnectionTimeout();
        int readTimeout = config.getReadTimeout();
        RestAssuredConfig raConfig = RestAssured.config()
                .httpClient(HttpClientConfig.httpClientConfig()
                        .setParam(CoreConnectionPNames.CONNECTION_TIMEOUT, connectionTimeout)
                        .setParam(CoreConnectionPNames.SO_TIMEOUT, readTimeout));
        RestAssured.config = raConfig;

        requestSpec = new RequestSpecBuilder()
                .setConfig(raConfig)
                .setBaseUri(config.getBaseUrl())
                .setContentType(ContentType.JSON)
                .setAccept(ContentType.JSON)
                .setRelaxedHTTPSValidation()
                .log(LogDetail.ALL)
                .build();

        responseSpec = new ResponseSpecBuilder()
                .log(LogDetail.ALL)
                .build();

        RestAssured.requestSpecification = requestSpec;
        RestAssured.responseSpecification = responseSpec;
        RestAssured.enableLoggingOfRequestAndResponseIfValidationFails();
    }
}
