from qa_gen_bot.structure_fixer import strip_long_literals_in_tests


def test_strips_l_suffix_on_int32_builder_fields_only():
    path = "src/test/java/com/demo/tests/T.java"
    files = {
        path: """
            OrderInputDto.builder().petId(1L).quantity(2L).build();
            client.getById(99L);
        """
    }
    result = strip_long_literals_in_tests(files)
    text = result.files[path]
    assert "petId(1L)" in text
    assert "quantity(2)" in text
    assert "getById(99L)" in text
