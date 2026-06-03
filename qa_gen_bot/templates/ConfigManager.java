package {{PACKAGE}}.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ConfigManager {

    private static final Logger log = LoggerFactory.getLogger(ConfigManager.class);
    private static final String CONFIG_FILE = "config.properties";
    private static volatile ConfigManager instance;
    private final Properties properties = new Properties();

    private ConfigManager() {
        try (InputStream in = getClass().getClassLoader().getResourceAsStream(CONFIG_FILE)) {
            if (in == null) {
                throw new IllegalStateException("Missing " + CONFIG_FILE);
            }
            properties.load(in);
            log.info("Loaded {}", CONFIG_FILE);
        } catch (IOException e) {
            throw new IllegalStateException("Cannot load " + CONFIG_FILE, e);
        }
    }

    public static ConfigManager getInstance() {
        if (instance == null) {
            synchronized (ConfigManager.class) {
                if (instance == null) {
                    instance = new ConfigManager();
                }
            }
        }
        return instance;
    }

    public String getBaseUrl() {
        return require("base.url");
    }

    public String getWireMockHost() {
        return require("wiremock.host");
    }

    public int getWireMockPort() {
        return Integer.parseInt(require("wiremock.port"));
    }

    public int getConnectionTimeout() {
        return Integer.parseInt(require("connection.timeout"));
    }

    public int getReadTimeout() {
        return Integer.parseInt(require("read.timeout"));
    }

    public String getWireMockBaseUrl() {
        return "http://" + getWireMockHost() + ":" + getWireMockPort();
    }

    private String require(String key) {
        String sys = System.getProperty(key);
        if (sys != null && !sys.isBlank()) {
            return sys;
        }
        String v = properties.getProperty(key);
        if (v == null) {
            throw new IllegalStateException("Missing property: " + key);
        }
        return v;
    }
}
