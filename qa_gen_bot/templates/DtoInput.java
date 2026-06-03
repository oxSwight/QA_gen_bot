package {{PACKAGE}}.dto.request;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request body DTO (scaffold). Additional fields may come from OpenAPI schema.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class {{DTO_INPUT}} {

    private String name;
    private Integer quantity;
    private String status;
}
