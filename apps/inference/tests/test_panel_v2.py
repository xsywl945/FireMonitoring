from fire_monitoring_inference.panel_v2 import READY, PanelDevice, PanelLink


class Transport:
    def __init__(self, device: PanelDevice) -> None:
        self.device = device
        self.prepared = False

    def prepare(self) -> None:
        self.prepared = True
        if self.device.exchange("HELLO") != READY:
            raise OSError("unexpected firmware")

    def request(self, command: str) -> str:
        self.prepare()
        return self.device.exchange(command)

    def close(self) -> None:
        self.prepared = False


def test_link_loss_forces_alternate_until_the_host_speaks() -> None:
    device = PanelDevice()
    assert device.exchange("HELLO") == READY
    assert device.exchange("MODE RED_SOLID") == "MODE RED_SOLID"
    device.advance(3000)
    assert device.effective_mode() == "ALT"
    assert device.exchange("STATUS") == "STATE RED_SOLID OPEN UP"


def test_mute_is_local_and_panel_link_sends_green_then_ping() -> None:
    device = PanelDevice()
    device.press_mute()
    link = PanelLink("", transport=Transport(device))
    link.start()
    link.close()
    assert device.host_mode == "GREEN"
    assert device.mute is True
