"""Prometheus remote write protocol implementation.

Implements the protobuf + snappy format required by Prometheus remote_write API.
"""

import struct
from typing import List, Tuple

import snappy

# Protobuf wire types
WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LENGTH_DELIMITED = 2


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = []
    while value > 127:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _encode_field(field_number: int, wire_type: int, data: bytes) -> bytes:
    """Encode a protobuf field."""
    tag = (field_number << 3) | wire_type
    return _encode_varint(tag) + data


def _encode_string(field_number: int, value: str) -> bytes:
    """Encode a string field."""
    encoded = value.encode("utf-8")
    return _encode_field(
        field_number, WIRE_LENGTH_DELIMITED, _encode_varint(len(encoded)) + encoded
    )


def _encode_double(field_number: int, value: float) -> bytes:
    """Encode a double field."""
    return _encode_field(field_number, WIRE_FIXED64, struct.pack("<d", value))


def _encode_int64(field_number: int, value: int) -> bytes:
    """Encode an int64 field as varint."""
    return _encode_field(field_number, WIRE_VARINT, _encode_varint(value))


def _encode_label(name: str, value: str) -> bytes:
    """Encode a Label message.

    message Label {
        string name = 1;
        string value = 2;
    }
    """
    return _encode_string(1, name) + _encode_string(2, value)


def _encode_sample(value: float, timestamp_ms: int) -> bytes:
    """Encode a Sample message.

    message Sample {
        double value = 1;
        int64 timestamp = 2;
    }
    """
    return _encode_double(1, value) + _encode_int64(2, timestamp_ms)


def _encode_timeseries(
    labels: List[Tuple[str, str]], samples: List[Tuple[float, int]]
) -> bytes:
    """Encode a TimeSeries message.

    message TimeSeries {
        repeated Label labels = 1;
        repeated Sample samples = 2;
    }
    """
    result = b""

    for name, value in labels:
        label_data = _encode_label(name, value)
        result += _encode_field(
            1, WIRE_LENGTH_DELIMITED, _encode_varint(len(label_data)) + label_data
        )

    for value, timestamp_ms in samples:
        sample_data = _encode_sample(value, timestamp_ms)
        result += _encode_field(
            2, WIRE_LENGTH_DELIMITED, _encode_varint(len(sample_data)) + sample_data
        )

    return result


def _encode_write_request(timeseries_list: List[bytes]) -> bytes:
    """Encode a WriteRequest message.

    message WriteRequest {
        repeated TimeSeries timeseries = 1;
    }
    """
    result = b""
    for ts_data in timeseries_list:
        result += _encode_field(
            1, WIRE_LENGTH_DELIMITED, _encode_varint(len(ts_data)) + ts_data
        )
    return result


def encode_remote_write(
    metrics: List[Tuple[str, dict, float, int]]
) -> bytes:
    """Encode metrics for Prometheus remote_write.

    Args:
        metrics: List of (metric_name, labels_dict, value, timestamp_ms)

    Returns:
        Snappy-compressed protobuf data ready for remote_write.
    """
    timeseries_list = []

    for metric_name, labels, value, timestamp_ms in metrics:
        # Build labels list - __name__ must be first
        label_pairs = [("__name__", metric_name)]
        label_pairs.extend(sorted(labels.items()))

        ts_data = _encode_timeseries(label_pairs, [(value, timestamp_ms)])
        timeseries_list.append(ts_data)

    write_request = _encode_write_request(timeseries_list)
    return snappy.compress(write_request)
