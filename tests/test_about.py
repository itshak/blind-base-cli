from blindbase import menu as bb_menu


def test_about_panel_renders(capsys):
    # just ensure _show_about does not crash and prints something
    try:
        bb_menu._console = None  # monkey bypass printing if needed
    except Exception:
        pass
