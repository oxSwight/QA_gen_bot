package {{PACKAGE}}.utils;

import com.github.javafaker.Faker;

import java.util.Locale;
import java.util.concurrent.ThreadLocalRandom;

public final class TestDataGenerator {

    private static final Faker FAKER = new Faker(Locale.ENGLISH);

    private TestDataGenerator() {
    }

    public static long randomId() {
        return ThreadLocalRandom.current().nextLong(1, 999_999);
    }

    public static String randomName(String prefix) {
        return prefix + "_" + FAKER.lorem().word() + FAKER.number().digits(4);
    }
}
