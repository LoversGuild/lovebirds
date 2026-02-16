from mashumaro.codecs import BasicDecoder, BasicEncoder

from lovebirds.models.events import Event, SmtpConfig


class TestEventRoundTrip:
    def test_encode_decode(self) -> None:
        data = {
            "event_id": "test_event",
            "mail": {
                "message_filter": {"html": "*.html", "plain": "*.txt"},
                "headers": {"From": "test@example.com"},
                "smtp": {"server": "smtp.example.com"},
            },
            "variables": {"key": "value"},
            "messages": {
                "welcome": {
                    "condition": "true",
                    "translations": ["en"],
                    "filename": "welcome.txt",
                    "variables": {"foo": "bar"},
                }
            },
        }
        decoder = BasicDecoder(Event)
        event = decoder.decode(data)
        assert event.event_id == "test_event"

        encoder = BasicEncoder(Event)
        encoded = encoder.encode(event)
        assert encoded["event_id"] == "test_event"
        assert encoded["mail"]["smtp"]["server"] == "smtp.example.com"


class TestSmtpConfigDefaults:
    def test_defaults(self) -> None:
        data = {"server": "smtp.example.com"}
        decoder = BasicDecoder(SmtpConfig)
        smtp = decoder.decode(data)
        assert smtp.tls is True
        assert smtp.messages_per_connection is None
