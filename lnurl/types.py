import re

from pydantic import Json, HttpUrl, PositiveInt, ValidationError, parse_obj_as
from pydantic.validators import str_validator
from urllib.parse import parse_qs
from typing import List, Optional, Tuple

from .exceptions import InvalidLnurlPayMetadata
from .helpers import _bech32_decode, _lnurl_clean, _lnurl_decode


class ReprMixin:
    def __repr__(self) -> str:  # pragma: nocover
        extra = ", ".join(f"{n}={getattr(self, n)!r}" for n in self.__slots__ if getattr(self, n) is not None)
        return f"{self.__class__.__name__}({super().__repr__()}, {extra})"


class Bech32(ReprMixin, str):
    """Bech32 string."""

    __slots__ = ("hrp", "data")

    def __new__(cls, bech32: str, **kwargs) -> object:
        return str.__new__(cls, bech32)

    def __init__(self, bech32: str, *, hrp: Optional[str] = None, data: Optional[List[int]] = None):
        str.__init__(bech32)
        self.hrp, self.data = (hrp, data) if hrp and data else self.__get_data__(bech32)

    @classmethod
    def __get_data__(cls, bech32: str) -> Tuple[str, List[int]]:
        return _bech32_decode(bech32)

    @classmethod
    def __get_validators__(cls):
        yield str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> "Bech32":
        hrp, data = cls.__get_data__(value)
        return cls(value, hrp=hrp, data=data)


class HttpsUrl(HttpUrl):
    """HTTPS URL."""

    allowed_schemes = {"https"}
    max_length = 2047  # https://stackoverflow.com/questions/417142/

    @property
    def base(self) -> str:
        return f"{self.scheme}://{self.host}{self.path}"

    @property
    def query_params(self) -> dict:
        return {k: v[0] for k, v in parse_qs(self.query).items()}


class LightningInvoice(Bech32):
    """Bech32 Lightning invoice."""

    @property
    def amount(self) -> int:
        a = re.search(r"(lnbc|lntb|lnbcrt)(\w+)", self.hrp).groups()[1]
        raise NotImplementedError

    @property
    def prefix(self) -> str:
        return re.search(r"(lnbc|lntb|lnbcrt)(\w+)", self.hrp).groups()[0]

    @property
    def h(self):
        raise NotImplementedError


class LightningNodeUri(ReprMixin, str):
    """Remote node address of form `node_key@ip_address:port_number`."""

    __slots__ = ("key", "ip", "port")

    def __new__(cls, uri: str, **kwargs) -> object:
        return str.__new__(cls, uri)

    def __init__(self, uri: str, *, key: Optional[str] = None, ip: Optional[str] = None, port: Optional[str] = None):
        str.__init__(uri)
        self.key = key
        self.ip = ip
        self.port = port

    @classmethod
    def __get_validators__(cls):
        yield str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> "LightningNodeUri":
        try:
            key, netloc = value.split("@")
            ip, port = netloc.split(":")
        except Exception:
            raise ValueError

        return cls(value, key=key, ip=ip, port=port)


class Lnurl(ReprMixin, str):
    __slots__ = ("bech32", "url")

    def __new__(cls, lightning: str, **kwargs) -> object:
        return str.__new__(cls, _lnurl_clean(lightning))

    def __init__(self, lightning: str, *, url: Optional[HttpsUrl] = None):
        bech32 = _lnurl_clean(lightning)
        str.__init__(bech32)
        self.bech32 = Bech32(bech32)
        self.url = url if url else self.__get_url__(bech32)

    @classmethod
    def __get_url__(cls, bech32: str) -> HttpsUrl:
        return parse_obj_as(HttpsUrl, _lnurl_decode(bech32))

    @classmethod
    def __get_validators__(cls):
        yield str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> "Lnurl":
        return cls(value, url=cls.__get_url__(value))

    @property
    def is_login(self) -> bool:
        return "tag" in self.url.query_params and self.url.query_params["tag"] == "login"


class LnurlPayMetadata(ReprMixin, str):
    valid_metadata_mime_types = ["text/plain"]

    __slots__ = ("list",)

    def __new__(cls, json_str: str, **kwargs) -> object:
        return str.__new__(cls, json_str)

    def __init__(self, json_str: str, *, json_obj: Optional[List] = None):
        str.__init__(json_str)
        self.list = json_obj if json_obj else self.__validate_metadata__(json_str)

    @classmethod
    def __validate_metadata__(cls, json_str: str) -> List[Tuple[str, str]]:
        try:
            data = parse_obj_as(Json[List[Tuple[str, str]]], json_str)
        except ValidationError:
            raise InvalidLnurlPayMetadata

        return [x for x in data if x[0] in cls.valid_metadata_mime_types]

    @classmethod
    def __get_validators__(cls):
        yield str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> "LnurlPayMetadata":
        return cls(value, json_obj=cls.__validate_metadata__(value))


class MilliSatoshi(PositiveInt):
    """A thousandth of a satoshi."""