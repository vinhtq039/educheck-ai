from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_app_starts_and_analysis_requires_a_file() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "AI kiểm tra học liệu"
    start_button = next(
        button for button in app.button if button.label == "Bắt đầu phân tích"
    )
    assert start_button.disabled is True


def test_clear_result_button_keeps_app_healthy() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    clear_button = next(button for button in app.button if button.label == "Xóa kết quả")
    clear_button.click().run()
    assert not app.exception

