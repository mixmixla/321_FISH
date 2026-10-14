import theme

def _skins():
    return [theme.get_skin("mist"), theme.get_skin("mist_dark")]

def test_keyset_superset_of_dialog_pal():
    for sk in _skins():
        gp = theme.game_shell_pal(sk)
        dp = theme.dialog_pal(sk)
        assert set(gp) >= set(dp)
        assert "card_bg" in gp

def test_light_branch_tokens():
    gp = theme.game_shell_pal(theme.get_skin("mist"))
    assert gp["accent"].upper() == "#16796C"
    assert gp["accent_hover"].upper() == "#11685C"
    assert gp["soft_bg"].upper() == "#EEF4F2"
    assert gp["border"].upper() == "#DCE6E2"

def test_dark_branch_tokens():
    gp = theme.game_shell_pal(theme.get_skin("mist_dark"))
    assert gp["accent"].upper() == "#86CDB3"
    assert gp["accent_hover"].upper() == "#9BDAC4"
    assert gp["soft_bg"].upper() == "#2B3C33"

def test_does_not_mutate_dialog_pal():
    sk = theme.get_skin("mist")
    before = dict(theme.dialog_pal(sk))
    theme.game_shell_pal(sk)
    assert theme.dialog_pal(sk) == before
