from focuscube.brainlink_source import PureTGAMBrainLinkParser


def frame(payload):
    checksum = (~(sum(payload) & 0xFF)) & 0xFF
    return bytes([0xAA, 0xAA, len(payload), *payload, checksum])


def test_pure_tgam_parser_emits_raw_samples():
    samples = []
    parser = PureTGAMBrainLinkParser(
        on_raw=samples.append,
        on_extend=lambda data: None,
    )

    parser.parse(frame([0x80, 0x02, 0x01, 0x2C]))

    assert samples == [300]


def test_pure_tgam_parser_emits_signed_raw_samples():
    samples = []
    parser = PureTGAMBrainLinkParser(
        on_raw=samples.append,
        on_extend=lambda data: None,
    )

    parser.parse(frame([0x80, 0x02, 0xFF, 0x38]))

    assert samples == [-200]


def test_pure_tgam_parser_emits_battery_and_version():
    extended = []
    parser = PureTGAMBrainLinkParser(
        on_raw=lambda raw: None,
        on_extend=extended.append,
    )

    parser.parse(frame([0x85, 0x03, 87, 1, 4]))

    assert extended[0].battery == 87
    assert extended[0].version == "1.4"
