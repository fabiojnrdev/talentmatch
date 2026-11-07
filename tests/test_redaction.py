from app.privacy.redaction import redact

SAMPLE = """Fábio de Araújo Abreu Júnior
Desenvolvedor Backend
Email: fabio.test@example.com | Tel: (86) 99999-8888
CPF 123.456.789-09
Rua das Flores, 123 - Centro
CEP 64000-000
https://github.com/fulano e linkedin.com/in/fulano
Estado civil: solteiro
Nascimento: 01/02/2000
Sou PCD e tenho laudo.
Trabalhei com FastAPI de 2021 a 2024.
Nasci em 05/06/1999.
"""


def test_removes_direct_identifiers_and_sensitive_lines():
    result = redact(SAMPLE)
    text = result.text
    for leaked in ["fabio.test@example.com", "99999-8888", "123.456.789-09", "Rua das Flores",
                   "64000-000", "github.com/fulano", "linkedin.com/in", "solteiro", "01/02/2000",
                   "05/06/1999", "PCD", "Fábio"]:
        assert leaked not in text, leaked
    assert "FastAPI" in text and "2021 a 2024" in text


def test_report_counts_only_never_values():
    report = redact(SAMPLE).report
    assert report["name"] == 1 and report["email"] == 1 and report["cpf"] == 1
    assert report["cep"] == 1 and report["address"] == 1 and report["sensitive_lines"] == 3
    assert report["date"] == 1 and report["phone"] >= 1 and report["url"] >= 2
    assert all(isinstance(v, int) for v in report.values())


def test_first_line_kept_when_not_a_name():
    result = redact("desenvolvedor backend python\nUsei FastAPI.")
    assert result.report["name"] == 0
    assert result.text.startswith("desenvolvedor")


def test_first_line_with_digits_or_single_word_is_not_name():
    assert redact("Currículo 2024\nTexto").report["name"] == 0
    assert redact("Maria\nTexto").report["name"] == 0
    assert redact("Um Dois Tres Quatro Cinco Seis Sete\nx").report["name"] == 0


def test_empty_text_and_blank_leading_lines():
    assert redact("").text == ""
    assert redact("\n\nJoão da Silva\nPython").report["name"] == 1


def test_stable_report_keys():
    assert set(redact("x").report) == {
        "name", "email", "url", "cpf", "phone", "date", "cep", "address", "sensitive_lines"
    }


def test_name_is_removed_from_body_too():
    result = redact("Maria Souza Lima\nAssinado: maria souza.\nUsei FastAPI com a Lima Tech.")
    assert "Maria" not in result.text and "Souza" not in result.text
    assert result.report["name"] >= 3
    assert "FastAPI" in result.text
