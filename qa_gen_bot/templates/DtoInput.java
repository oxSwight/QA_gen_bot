package {{PACKAGE}}.dto.request;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request body DTO (scaffold). LLM may extend fields from OpenAPI schema.
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
